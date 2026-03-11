#!/usr/bin/env python3
"""netbuoy - Network connectivity monitor & guardian for macOS."""

import argparse
import curses
import json
import platform
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PING_TARGET = "1.1.1.1"  # Cloudflare — privacy-friendly
FALLBACK_PING_TARGET = "9.9.9.9"  # Quad9
DEFAULT_INTERVAL = 2  # seconds between pings
DEFAULT_SPEED_INTERVAL = 5  # minutes between speed tests
DB_DIR = Path.home() / ".netbuoy"
DB_PATH = DB_DIR / "history.db"
VPN_VERIFY_INTERVAL = 60  # seconds between IP-based VPN verification checks
VPN_CHECK_URL = "https://ipinfo.io/json"  # Free, no API key, returns ASN/org info

# Known VPN provider identifiers (matched case-insensitively against ASN org name)
VPN_ORG_KEYWORDS = [
    "proton", "protonvpn", "proton ag",
    "nordvpn", "nord security",
    "mullvad",
    "expressvpn",
    "surfshark",
    "private internet access", "pia",
    "cyberghost",
    "ivpn",
    "windscribe",
    "torguard",
    "airvpn",
    "hide.me",
    "astrill",
    "purevpn",
    "ipvanish",
    "hotspot shield",
    "tunnelbear",
    "mozilla vpn",
    "wireguard",
    "datacamp",  # hosting commonly used by VPNs
    "m247",  # infrastructure provider for many VPN services
    "hostinger",
    "leaseweb",
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def init_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    # Restrict directory permissions to owner only
    DB_DIR.chmod(0o700)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ping_log (
            ts REAL PRIMARY KEY,
            ok INTEGER NOT NULL,
            latency_ms REAL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS speed_log (
            ts REAL PRIMARY KEY,
            download_mbps REAL,
            upload_mbps REAL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ping_ts ON ping_log(ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_speed_ts ON speed_log(ts)")
    conn.commit()
    return conn


def record_ping(conn, ok, latency_ms=None):
    now = time.time()
    conn.execute(
        "INSERT OR REPLACE INTO ping_log (ts, ok, latency_ms) VALUES (?, ?, ?)",
        (now, int(ok), latency_ms),
    )
    conn.commit()


def record_speed(conn, download_mbps, upload_mbps):
    now = time.time()
    conn.execute(
        "INSERT OR REPLACE INTO speed_log (ts, download_mbps, upload_mbps) VALUES (?, ?, ?)",
        (now, download_mbps, upload_mbps),
    )
    conn.commit()


def uptime_percent(conn, seconds):
    """Return (percent, total_checks) for the last `seconds` window."""
    cutoff = time.time() - seconds
    row = conn.execute(
        "SELECT COUNT(*), SUM(ok) FROM ping_log WHERE ts >= ?", (cutoff,)
    ).fetchone()
    total, ok = row[0], row[1] or 0
    if total == 0:
        return None, 0
    return (ok / total) * 100, total


def uptime_since(conn, since_ts):
    row = conn.execute(
        "SELECT COUNT(*), SUM(ok) FROM ping_log WHERE ts >= ?", (since_ts,)
    ).fetchone()
    total, ok = row[0], row[1] or 0
    if total == 0:
        return None, 0
    return (ok / total) * 100, total


def uptime_all_time(conn):
    row = conn.execute("SELECT COUNT(*), SUM(ok) FROM ping_log").fetchone()
    total, ok = row[0], row[1] or 0
    if total == 0:
        return None, 0
    return (ok / total) * 100, total


def latest_speed(conn):
    row = conn.execute(
        "SELECT download_mbps, upload_mbps, ts FROM speed_log ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    return row  # (down, up, ts) or None


# ---------------------------------------------------------------------------
# Connectivity check
# ---------------------------------------------------------------------------


def ping_check(target, timeout=2):
    """Return (ok, latency_ms)."""
    try:
        # macOS ping -W takes milliseconds; Linux takes seconds
        wait_val = str(timeout * 1000) if platform.system() == "Darwin" else str(timeout)
        result = subprocess.run(
            ["ping", "-c", "1", "-W", wait_val, target],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
        if result.returncode == 0:
            m = re.search(r"time[=<]\s*([\d.]+)\s*ms", result.stdout)
            latency = float(m.group(1)) if m else None
            return True, latency
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return False, None


# ---------------------------------------------------------------------------
# Network interfaces
# ---------------------------------------------------------------------------


def get_interfaces():
    """Return list of dicts with interface info."""
    interfaces = []
    try:
        result = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        blocks = result.stdout.strip().split("\n\n")
        for block in blocks:
            info = {}
            for line in block.split("\n"):
                if line.startswith("Hardware Port:"):
                    info["port"] = line.split(":", 1)[1].strip()
                elif line.startswith("Device:"):
                    info["device"] = line.split(":", 1)[1].strip()
            if "device" in info:
                # Get IP address
                try:
                    ip_result = subprocess.run(
                        ["ipconfig", "getifaddr", info["device"]],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    info["ip"] = ip_result.stdout.strip() if ip_result.returncode == 0 else None
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    info["ip"] = None
                # Check if active
                try:
                    status_result = subprocess.run(
                        ["ifconfig", info["device"]],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    info["active"] = "status: active" in status_result.stdout
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    info["active"] = False
                interfaces.append(info)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return interfaces


def is_wifi_on():
    try:
        result = subprocess.run(
            ["networksetup", "-getairportpower", "en0"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "on" in result.stdout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def set_wifi(on):
    state = "on" if on else "off"
    try:
        subprocess.run(
            ["networksetup", "-setairportpower", "en0", state],
            capture_output=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


# ---------------------------------------------------------------------------
# VPN detection & management
# ---------------------------------------------------------------------------


def is_vpn_connected():
    """Check for VPN tunnel interfaces (utun) via scutil."""
    try:
        result = subprocess.run(
            ["scutil", "--nwi"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Look for utun interfaces which indicate a VPN tunnel
        utun_lines = [l for l in result.stdout.split("\n") if "utun" in l]
        if utun_lines:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: check ifconfig for tunnel interfaces
    try:
        result = subprocess.run(
            ["ifconfig"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Look for utun interfaces that are UP with an inet address
        current_iface = None
        has_inet = False
        for line in result.stdout.split("\n"):
            if not line.startswith("\t") and ":" in line:
                if current_iface and current_iface.startswith("utun") and has_inet:
                    return True
                current_iface = line.split(":")[0]
                has_inet = False
            elif "inet " in line and current_iface and current_iface.startswith("utun"):
                has_inet = True
        if current_iface and current_iface.startswith("utun") and has_inet:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return False


def verify_vpn_ip(baseline_ip=None):
    """Empirically verify VPN by checking public IP via ipinfo.io.

    Uses two signals:
    1. ASN org name matches known VPN providers
    2. Public IP differs from the baseline ISP IP (if known)

    Returns a dict with:
        verified: bool — True if IP appears to be behind a VPN
        ip: str or None — the current public IP
        org: str or None — ASN organization name
        reason: str — why we think VPN is active or not
    Returns None if the check fails (e.g. no connectivity).
    """
    try:
        req = urllib.request.Request(
            VPN_CHECK_URL,
            headers={"User-Agent": "netbuoy", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        # Sanitize API response: strip control characters and truncate
        ip = re.sub(r"[^\x20-\x7E]", "", str(data.get("ip", "")))[:45]
        org = re.sub(r"[^\x20-\x7E]", "", str(data.get("org", "")))[:100]
        org_lower = org.lower()

        # Check if org matches a known VPN provider
        org_match = any(kw in org_lower for kw in VPN_ORG_KEYWORDS)

        # Check if IP changed from baseline (ISP) IP
        ip_changed = baseline_ip is not None and ip != baseline_ip

        verified = org_match or ip_changed
        if org_match:
            reason = f"org matches VPN provider: {org}"
        elif ip_changed:
            reason = f"IP differs from baseline ({baseline_ip})"
        else:
            reason = f"org looks like ISP: {org}"

        return {
            "verified": verified,
            "ip": ip,
            "org": org,
            "reason": reason,
        }
    except Exception:
        return None


def notify_vpn_unprotected(tunnel_up=False):
    """Send a macOS notification that VPN is not protecting traffic."""
    if tunnel_up:
        msg = "VPN tunnel is up but your IP is NOT protected — reconnect in Proton VPN"
    else:
        msg = "VPN is down — reconnect in Proton VPN"
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{msg}" '
             f'with title "netbuoy" sound name "Basso"'],
            capture_output=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


# ---------------------------------------------------------------------------
# Transmission safety kill
# ---------------------------------------------------------------------------


def kill_transmission():
    """Gracefully quit Transmission.app if running."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "Transmission"],
            capture_output=True,
            timeout=3,
        )
        if result.returncode == 0:
            # Try graceful quit first
            subprocess.run(
                ["osascript", "-e", 'tell application "Transmission" to quit'],
                capture_output=True,
                timeout=5,
            )
            time.sleep(1)
            # Force kill if still running
            recheck = subprocess.run(
                ["pgrep", "-x", "Transmission"],
                capture_output=True,
                timeout=3,
            )
            if recheck.returncode == 0:
                subprocess.run(
                    ["killall", "Transmission"],
                    capture_output=True,
                    timeout=3,
                )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


# ---------------------------------------------------------------------------
# Speed test
# ---------------------------------------------------------------------------


def run_speed_test():
    """Run a speed test. Returns (download_mbps, upload_mbps) or None."""
    try:
        import speedtest

        st = speedtest.Speedtest()
        st.get_best_server()
        st.download()
        st.upload()
        results = st.results.dict()
        down = results["download"] / 1_000_000
        up = results["upload"] / 1_000_000
        return down, up
    except Exception:
        pass

    # Fallback: curl-based download test (download only)
    try:
        start = time.time()
        result = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-w", "%{size_download}",
             "https://speed.cloudflare.com/__down?bytes=10000000"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        elapsed = time.time() - start
        if result.returncode == 0 and elapsed > 0:
            bytes_downloaded = int(result.stdout.strip())
            mbps = (bytes_downloaded * 8) / (elapsed * 1_000_000)
            return mbps, None
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass

    return None


# ---------------------------------------------------------------------------
# Terminal display (curses)
# ---------------------------------------------------------------------------


def format_uptime(pct):
    if pct is None:
        return "  --  "
    return f"{pct:5.1f}%"


def format_duration(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"


def draw_status_bar(win, y, x, width, pct, label):
    """Draw a colored status bar."""
    win.addstr(y, x, f"{label}: ", curses.A_BOLD)
    label_len = len(label) + 2
    bar_width = width - label_len - 8  # room for percentage text
    if pct is None:
        win.addstr(y, x + label_len, "waiting for data...")
        return

    filled = int(bar_width * pct / 100)
    if pct >= 99:
        color = curses.color_pair(1)  # green
    elif pct >= 90:
        color = curses.color_pair(3)  # yellow
    else:
        color = curses.color_pair(2)  # red

    bar = "█" * filled + "░" * (bar_width - filled)
    win.addstr(y, x + label_len, bar, color)
    win.addstr(y, x + label_len + bar_width + 1, f"{pct:5.1f}%")


class Display:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_CYAN, -1)
        stdscr.nodelay(True)
        stdscr.timeout(100)

    def render(self, state):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        if h < 10 or w < 40:
            self.stdscr.addstr(0, 0, "Terminal too small")
            self.stdscr.refresh()
            return

        y = 0
        # Header
        self.stdscr.addstr(y, 0, " NETBUOY ", curses.A_REVERSE | curses.A_BOLD)
        self.stdscr.addstr(y, 10, f" Network Monitor", curses.A_DIM)
        runtime = format_duration(time.time() - state["start_time"])
        runtime_str = f"uptime: {runtime}"
        if w > len(runtime_str) + 12:
            self.stdscr.addstr(y, w - len(runtime_str) - 1, runtime_str, curses.A_DIM)
        y += 2

        # Current status
        if state["connected"]:
            self.stdscr.addstr(y, 0, " CONNECTED ", curses.color_pair(1) | curses.A_BOLD | curses.A_REVERSE)
            if state["latency"] is not None:
                self.stdscr.addstr(y, 13, f"{state['latency']:.0f}ms", curses.color_pair(1))
        else:
            self.stdscr.addstr(y, 0, " DISCONNECTED ", curses.color_pair(2) | curses.A_BOLD | curses.A_REVERSE)
        y += 1

        # VPN status
        if state["vpn_enabled"]:
            # Line 1: tunnel status
            if state["vpn_tunnel"]:
                self.stdscr.addstr(y, 0, " TUNNEL ", curses.color_pair(1) | curses.A_REVERSE)
                self.stdscr.addstr(y, 9, "Up", curses.color_pair(1))
            else:
                self.stdscr.addstr(y, 0, " TUNNEL ", curses.color_pair(2) | curses.A_REVERSE)
                self.stdscr.addstr(y, 9, "Down", curses.color_pair(2) | curses.A_BOLD)
            y += 1

            # Line 2: IP verification status
            verified = state["vpn_verified"]
            if verified is None:
                self.stdscr.addstr(y, 0, " VPN IP ", curses.color_pair(3) | curses.A_REVERSE)
                self.stdscr.addstr(y, 9, "Checking...", curses.color_pair(3))
            elif verified:
                self.stdscr.addstr(y, 0, " VPN IP ", curses.color_pair(1) | curses.A_REVERSE)
                detail = "Verified"
                if state["vpn_ip"]:
                    detail += f"  {state['vpn_ip']}"
                if state["vpn_org"]:
                    detail += f"  ({state['vpn_org']})"
                self.stdscr.addstr(y, 9, detail[:w - 10], curses.color_pair(1))
            else:
                self.stdscr.addstr(y, 0, " VPN IP ", curses.color_pair(2) | curses.A_REVERSE)
                detail = "NOT Protected"
                if state["vpn_org"]:
                    detail += f"  ({state['vpn_org']})"
                self.stdscr.addstr(y, 9, detail[:w - 10], curses.color_pair(2) | curses.A_BOLD)

            # Show age of last verification
            if state["vpn_verify_age"] is not None and w > 50:
                age_str = f"  [{format_duration(state['vpn_verify_age'])} ago]"
                try:
                    self.stdscr.addstr(age_str, curses.A_DIM)
                except curses.error:
                    pass
        y += 2

        # Uptime bars
        safe_w = min(w - 1, 78)
        windows = [
            ("1 min", state["uptime_1m"]),
            ("1 hour", state["uptime_1h"]),
            ("1 day", state["uptime_1d"]),
            ("Session", state["uptime_session"]),
            ("All time", state["uptime_all"]),
        ]
        self.stdscr.addstr(y, 0, "Uptime:", curses.A_BOLD | curses.A_UNDERLINE)
        y += 1
        for label, pct in windows:
            if y >= h - 4:
                break
            draw_status_bar(self.stdscr, y, 1, safe_w, pct, f"{label:>8s}")
            y += 1
        y += 1

        # Interfaces
        if y < h - 3 and state["interfaces"]:
            self.stdscr.addstr(y, 0, "Interfaces:", curses.A_BOLD | curses.A_UNDERLINE)
            y += 1
            for iface in state["interfaces"]:
                if y >= h - 2:
                    break
                port = iface.get("port", "?")
                dev = iface.get("device", "?")
                ip = iface.get("ip") or "no IP"
                active = iface.get("active", False)
                color = curses.color_pair(1) if active else curses.A_DIM
                marker = "●" if active else "○"
                line = f" {marker} {port} ({dev}): {ip}"
                self.stdscr.addstr(y, 0, line[:w - 1], color)
                y += 1
            y += 1

        # Speed test
        if y < h - 1 and state["speed"]:
            down, up, ts = state["speed"]
            age = format_duration(time.time() - ts)
            speed_str = f"Speed: ↓ {down:.1f} Mbps"
            if up is not None:
                speed_str += f"  ↑ {up:.1f} Mbps"
            speed_str += f"  ({age} ago)"
            self.stdscr.addstr(y, 0, speed_str, curses.color_pair(4))
            y += 1

        # Footer
        if h > y + 1:
            footer = "q: quit  |  ping: " + state["ping_target"]
            self.stdscr.addstr(h - 1, 0, footer[:w - 1], curses.A_DIM)

        self.stdscr.refresh()

    def check_quit(self):
        try:
            key = self.stdscr.getch()
            return key == ord("q")
        except curses.error:
            return False


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main_loop(stdscr, args):
    display = Display(stdscr)
    conn = init_db()
    start_time = time.time()
    last_speed_test = 0
    last_vpn_verify = 0
    speed_result = latest_speed(conn)
    transmission_killed = False
    vpn_notified = False
    baseline_ip = None  # First IP seen without VPN tunnel — assumed to be ISP IP
    speed_thread_running = False
    db_lock = threading.Lock()

    # Turn off WiFi by default
    if not args.keep_wifi:
        if is_wifi_on():
            set_wifi(False)

    state = {
        "connected": False,
        "latency": None,
        "vpn_tunnel": False,       # Local check: utun interface exists
        "vpn_verified": None,      # IP check: None=pending, True/False=result
        "vpn_ip": None,            # Public IP from last verification
        "vpn_org": None,           # ASN org from last verification
        "vpn_reason": None,        # Why we think VPN is/isn't active
        "vpn_verify_age": None,    # Seconds since last successful verify
        "vpn_enabled": not args.no_vpn,
        "interfaces": [],
        "uptime_1m": None,
        "uptime_1h": None,
        "uptime_1d": None,
        "uptime_session": None,
        "uptime_all": None,
        "speed": speed_result,
        "start_time": start_time,
        "ping_target": args.ping_target,
    }

    ping_targets = [args.ping_target, FALLBACK_PING_TARGET]
    last_ping = 0
    last_interface_check = 0
    last_vpn_tunnel_check = 0

    while True:
        now = time.time()

        # Ping check
        if now - last_ping >= args.interval:
            ok, latency = ping_check(ping_targets[0])
            if not ok and ping_targets[0] != FALLBACK_PING_TARGET:
                ok, latency = ping_check(ping_targets[1])
            with db_lock:
                record_ping(conn, ok, latency)
            state["connected"] = ok
            state["latency"] = latency
            last_ping = now

        # Interface check (every 10s to reduce overhead)
        if now - last_interface_check >= 10:
            state["interfaces"] = get_interfaces()
            last_interface_check = now

        # VPN check
        if state["vpn_enabled"]:
            # Local tunnel check (every 5s to reduce subprocess overhead)
            if now - last_vpn_tunnel_check >= 5:
                vpn_tunnel = is_vpn_connected()
                state["vpn_tunnel"] = vpn_tunnel
                last_vpn_tunnel_check = now
                # Tunnel dropped — invalidate stale IP verification so we react immediately
                if not vpn_tunnel:
                    state["vpn_verified"] = None
            vpn_tunnel = state["vpn_tunnel"]

            # Periodic empirical IP check
            if state["connected"] and (now - last_vpn_verify >= VPN_VERIFY_INTERVAL):
                result = verify_vpn_ip(baseline_ip)
                if result:
                    state["vpn_verified"] = result["verified"]
                    state["vpn_ip"] = result["ip"]
                    state["vpn_org"] = result["org"]
                    state["vpn_reason"] = result["reason"]
                    last_vpn_verify = now
                    # Learn baseline IP: if no tunnel is up, this is our ISP IP
                    if not vpn_tunnel and baseline_ip is None and result["ip"]:
                        baseline_ip = result["ip"]

            if last_vpn_verify > 0:
                state["vpn_verify_age"] = now - last_vpn_verify

            # Decide if VPN is truly protecting us:
            # Trust verified status if available, otherwise fall back to tunnel check
            if state["vpn_verified"] is not None:
                vpn_protecting = state["vpn_verified"]
            else:
                vpn_protecting = vpn_tunnel

            if not vpn_protecting:
                # Kill Transmission if VPN is not protecting
                if not args.no_kill and not transmission_killed:
                    kill_transmission()
                    transmission_killed = True

                # Notify user (once per incident)
                if not vpn_notified:
                    notify_vpn_unprotected(tunnel_up=vpn_tunnel)
                    vpn_notified = True
            else:
                transmission_killed = False
                vpn_notified = False

        # Uptime stats
        with db_lock:
            state["uptime_1m"], _ = uptime_percent(conn, 60)
            state["uptime_1h"], _ = uptime_percent(conn, 3600)
            state["uptime_1d"], _ = uptime_percent(conn, 86400)
            state["uptime_session"], _ = uptime_since(conn, start_time)
            state["uptime_all"], _ = uptime_all_time(conn)

        # Speed test (threaded to avoid blocking UI)
        speed_interval_sec = args.speed_interval * 60
        if now - last_speed_test >= speed_interval_sec and not speed_thread_running:
            speed_thread_running = True
            last_speed_test = now

            def _speed_worker():
                nonlocal speed_thread_running
                try:
                    r = run_speed_test()
                    if r:
                        d, u = r
                        with db_lock:
                            record_speed(conn, d, u)
                        state["speed"] = (d, u, time.time())
                finally:
                    speed_thread_running = False

            threading.Thread(target=_speed_worker, daemon=True).start()

        # Render
        display.render(state)

        # Check for quit
        if display.check_quit():
            break

        time.sleep(0.1)

    conn.close()


def main():
    if platform.system() != "Darwin":
        print("Warning: netbuoy is designed for macOS. Some features may not work.", file=sys.stderr)

    parser = argparse.ArgumentParser(
        description="netbuoy - Network connectivity monitor & guardian for macOS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"netbuoy {__version__}",
    )
    parser.add_argument(
        "--keep-wifi",
        action="store_true",
        help="Don't turn off WiFi on start",
    )
    parser.add_argument(
        "--ping-target",
        default=DEFAULT_PING_TARGET,
        help=f"Ping target host (default: {DEFAULT_PING_TARGET})",
    )
    parser.add_argument(
        "--no-vpn",
        action="store_true",
        help="Disable VPN monitoring and management",
    )
    parser.add_argument(
        "--no-kill",
        action="store_true",
        help="Don't kill Transmission.app when VPN is down",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"Ping interval in seconds (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--speed-interval",
        type=float,
        default=DEFAULT_SPEED_INTERVAL,
        help=f"Speed test interval in minutes (default: {DEFAULT_SPEED_INTERVAL})",
    )
    args = parser.parse_args()

    # Input validation
    if args.interval <= 0:
        parser.error("--interval must be positive")
    if args.speed_interval <= 0:
        parser.error("--speed-interval must be positive")
    if args.ping_target.startswith("-"):
        parser.error("--ping-target must be a hostname or IP, not a flag")

    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    curses.wrapper(lambda stdscr: main_loop(stdscr, args))


if __name__ == "__main__":
    main()

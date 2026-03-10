# Testing Plan

Netbuoy interacts heavily with macOS system services, so testing requires a mix of automated unit tests, manual verification on macOS, and simulated failure scenarios.

## 1. Unit Tests (Python — can run anywhere)

These test pure logic with no system dependencies. Run with `python3 -m pytest tests/`.

### Database functions
- `init_db()` creates `~/.netbuoy/history.db` with correct schema
- `record_ping()` inserts rows, handles duplicate timestamps (REPLACE)
- `uptime_percent()` returns correct percentage for known data over 60s, 3600s, 86400s windows
- `uptime_percent()` returns `(None, 0)` when no data exists
- `uptime_since()` and `uptime_all_time()` calculate correctly
- `record_speed()` / `latest_speed()` round-trip correctly
- DB uses WAL journal mode

### Uptime calculation edge cases
- 100% uptime (all pings OK)
- 0% uptime (all pings fail)
- Mixed results across window boundaries (e.g., 50% in last minute, 90% in last hour)
- Rolling window excludes old data correctly
- Session uptime vs all-time uptime diverge correctly

### CLI argument parsing
- Default values: interval=2, speed-interval=5, ping-target=1.1.1.1, vpn-mode=fastest
- `--keep-wifi` sets flag
- `--no-vpn` disables VPN monitoring
- `--no-kill` disables Transmission kill
- `--vpn-mode random` accepted, invalid values rejected
- `--interval` and `--speed-interval` accept floats
- `--help` exits 0

### VPN IP verification logic
- `verify_vpn_ip()` returns `verified=True` when org contains "Proton AG"
- `verify_vpn_ip()` returns `verified=True` when org contains "M247" (common VPN infra)
- `verify_vpn_ip()` returns `verified=False` when org is "Comcast" (residential ISP)
- `verify_vpn_ip()` returns `verified=True` when IP differs from baseline, even with ISP-like org
- `verify_vpn_ip()` returns `None` on network failure
- Baseline IP is learned only when tunnel is down
- Keyword matching is case-insensitive
- All keywords in `VPN_ORG_KEYWORDS` are lowercase

### Display helpers
- `format_duration()`: 45→"45s", 90→"1m 30s", 3661→"1h 1m"
- `format_uptime()`: None→"  --  ", 99.5→"99.5%", 100.0→"100.0%"

### Ping parsing
- Extracts latency from `time=12.3 ms` format
- Extracts latency from `time<1 ms` format
- Returns `(False, None)` on timeout

## 2. Integration Tests (macOS only)

These require a real macOS machine. Run manually or in macOS CI.

### Connectivity monitoring
- [ ] Ping succeeds against 1.1.1.1 with valid latency extracted
- [ ] Ping falls back to 9.9.9.9 when primary target is unreachable (test with `--ping-target 192.0.2.1` — reserved/unreachable)
- [ ] Ping results are recorded in SQLite DB
- [ ] Uptime percentages update in real-time on the dashboard

### Network interface detection
- [ ] `get_interfaces()` lists Wi-Fi (en0) and Ethernet interfaces
- [ ] Active interfaces show IP addresses
- [ ] Inactive interfaces show "no IP" or are hidden
- [ ] Interface list updates when cable is plugged/unplugged

### WiFi management
- [ ] WiFi is turned off on start (default behavior)
- [ ] `--keep-wifi` prevents WiFi from being turned off
- [ ] `is_wifi_on()` correctly reports WiFi state before and after toggle
- [ ] WiFi device name is correct (may not always be en0 on all Macs — potential issue)

### VPN tunnel detection
- [ ] `is_vpn_connected()` returns True when Proton VPN is connected
- [ ] `is_vpn_connected()` returns False when Proton VPN is disconnected
- [ ] Detection works via `scutil --nwi` path
- [ ] Detection works via `ifconfig` fallback when scutil fails

### VPN IP verification
- [ ] `verify_vpn_ip()` returns `verified=True` with Proton VPN connected (org should contain "Proton")
- [ ] `verify_vpn_ip()` returns `verified=False` with VPN disconnected (org should be ISP name)
- [ ] Baseline IP is learned on first check without VPN tunnel
- [ ] After VPN connects, IP differs from baseline → verified=True even if org keyword misses
- [ ] Verification runs every 60 seconds (check with debug logging)
- [ ] Network timeout doesn't crash the app (disconnect ethernet during check)

### VPN recycling
- [ ] Proton VPN reconnects via osascript when tunnel is down and network is up
- [ ] `--vpn-mode fastest` triggers "Fastest" menu item
- [ ] `--vpn-mode random` triggers "Random" menu item
- [ ] 30-second cooldown prevents rapid recycle attempts
- [ ] Recycle does not trigger when `--no-vpn` is set

### Transmission safety kill
- [ ] Transmission.app is killed when VPN verified status is False
- [ ] Graceful quit (osascript) is attempted before killall
- [ ] Kill only happens once (not every loop cycle)
- [ ] Transmission is allowed to run again after VPN is re-verified
- [ ] `--no-kill` prevents Transmission from being killed

### Speed test
- [ ] Speed test runs on schedule (default every 5 minutes)
- [ ] `speedtest-cli` library is used when available
- [ ] Falls back to curl-based Cloudflare download test when speedtest-cli is missing
- [ ] Results are recorded in SQLite and displayed in UI
- [ ] Speed test doesn't block the main loop for more than ~30 seconds

## 3. Display / UI Tests (macOS, manual)

### Curses dashboard (Python version)
- [ ] Dashboard renders without crashing on standard Terminal.app (80x24)
- [ ] Dashboard handles small terminal gracefully (shows "Terminal too small")
- [ ] Terminal resize doesn't crash
- [ ] All uptime bars render with correct colors: green (≥99%), yellow (≥90%), red (<90%)
- [ ] Connection status shows CONNECTED (green) / DISCONNECTED (red)
- [ ] VPN section shows both TUNNEL and VPN IP lines
- [ ] VPN IP line shows public IP and org name
- [ ] VPN verification age is displayed (e.g., "[45s ago]")
- [ ] Speed test results display with down/up values and age
- [ ] Interface list shows active (●) and inactive (○) markers
- [ ] Footer shows quit key and ping target
- [ ] `q` key quits cleanly
- [ ] Ctrl+C quits cleanly

### ANSI display (Shell version)
- [ ] Same visual checks as above (minus uptime bars — shell only shows session %)
- [ ] Colors render correctly in Terminal.app, iTerm2, and tmux
- [ ] Cursor is hidden during run and restored on exit
- [ ] `q` key and Ctrl+C both exit cleanly with session summary

## 4. Failure Scenario Tests

### Network failures
- [ ] Unplug ethernet → status changes to DISCONNECTED within one interval
- [ ] Replug ethernet → status changes to CONNECTED
- [ ] VPN recycle is triggered after ethernet reconnect if VPN tunnel is down
- [ ] Transmission is killed during the disconnected period if VPN drops

### VPN failures
- [ ] Disconnect Proton VPN manually → TUNNEL shows Down, VPN IP shows NOT Protected (after next verify)
- [ ] Transmission is killed after VPN verification confirms no VPN
- [ ] VPN recycle attempt is made within 30 seconds
- [ ] Reconnect Proton VPN manually → both TUNNEL and VPN IP recover

### API failures
- [ ] `ipinfo.io` unreachable (e.g., DNS blocked) → VPN IP shows "Checking..." indefinitely, falls back to tunnel check for safety decisions
- [ ] `ipinfo.io` returns malformed JSON → no crash, returns None
- [ ] `ipinfo.io` returns unexpected schema (missing `org` field) → graceful handling

### Edge cases
- [ ] Start with no network at all → DISCONNECTED, no VPN checks, no crashes
- [ ] Start with VPN already connected → both tunnel and IP verify detect it
- [ ] DB file is corrupted/missing → `init_db()` recreates it
- [ ] Multiple netbuoy instances → SQLite WAL handles concurrent writes
- [ ] Very long runtime (>24h) → uptime windows remain accurate, no memory leaks from accumulating state

## 5. Shell Version Parity

Verify the shell version matches Python behavior for shared features:

- [ ] Ping check with fallback
- [ ] WiFi off by default / --keep-wifi
- [ ] VPN tunnel detection (scutil + ifconfig fallback)
- [ ] VPN IP verification (curl/wget + grep parsing matches Python's urllib+json)
- [ ] Baseline IP learning
- [ ] VPN recycle with cooldown
- [ ] Transmission kill with one-shot guard
- [ ] All CLI flags accepted and functional
- [ ] Clean exit on q and Ctrl+C

## 6. Running Tests

```bash
# Unit tests (once test files exist)
python3 -m pytest tests/ -v

# Syntax checks
python3 -m py_compile netbuoy.py
bash -n netbuoy.sh

# Quick smoke test (runs for 10 seconds then exits)
timeout 10 python3 netbuoy.py --no-vpn --keep-wifi --interval 1 || true

# Shell smoke test
timeout 10 bash netbuoy.sh --no-vpn --keep-wifi --interval 1 || true
```

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Netbuoy is a macOS CLI network guardian that monitors connectivity in real-time, verifies VPN protection (Proton VPN), and guards against data leakage. It has two versions:

- **`netbuoy.py`** — Full-featured Python version with curses UI, SQLite history, speed tests
- **`netbuoy.sh`** — Minimal shell-only version with no dependencies (session stats only, no DB/speed tests)

## Build & Install

```bash
make install       # Python version → ~/.local/bin/netbuoy (virtualenv + pip deps)
make install-sh    # Shell-only version → ~/.local/bin/netbuoy
make uninstall     # Remove from ~/.local/bin and clean up data
```

The installer auto-adds `~/.local/bin` to PATH if needed. Override with `make install PREFIX=/custom/path`.

## Running Locally

```bash
python3 netbuoy.py --help          # Show all options
python3 netbuoy.py --keep-wifi     # Run without disabling WiFi
python3 netbuoy.py --no-vpn        # Run without VPN management
bash netbuoy.sh --help             # Shell version
```

## Testing

```bash
python3 -m pytest tests/ -v                         # Run all tests
python3 -m pytest tests/ --cov=netbuoy              # With coverage
python3 -m pytest tests/test_vpn_verify.py -v       # Single test file
python3 -m pytest tests/test_ping.py::TestPingCheck  # Single test class
bash -n netbuoy.sh                                   # Shell syntax check
```

## Development Workflow

All work happens on the `dev` branch. Never commit directly to `main`.

### Before committing to dev
1. Run `python3 -m pytest tests/ -v` — all tests must pass
2. Run `python3 -m py_compile netbuoy.py && bash -n netbuoy.sh` — syntax check
3. Write tests for any new or changed functionality

### Before opening a PR to main
1. **Comprehensive code review** — read through all changed files for correctness, style, and edge cases
2. **Security audit** — check for command injection in subprocess calls, input validation, data leakage risks, and safe handling of external API responses
3. **Test coverage** — run `python3 -m pytest tests/ --cov=netbuoy --cov-report=term-missing` and identify any untested paths in changed code
4. **Missing tests** — write tests for any gaps found during review
5. **Doc updates** — update README.md, CLAUDE.md, and TESTING.md if behavior changed
6. **Coverage badge** — update the coverage percentage in README.md if it changed

### PR format
PRs to `main` must include:
- Summary of all changes with rationale
- List of every test and what it verifies
- Test results (pass/fail count, coverage %)
- Security audit findings (even if clean — state what was checked)
- Any known limitations or follow-up work

### Maintaining parity
When changing behavior in `netbuoy.py`, check if the same change is needed in `netbuoy.sh` (and vice versa). Key areas that must stay in sync:
- VPN keyword list (`VPN_ORG_KEYWORDS` in Python, `for kw in ...` loop in shell)
- CLI flags and their defaults
- VPN protection logic (tunnel + verified → safety actions)
- Notification behavior when VPN is unprotected
- Ping targets and fallback behavior
- API response sanitization

## Architecture

### Main Loop (`netbuoy.py`)
The main loop runs every `--interval` seconds (default 2) inside `curses.wrapper`:
1. **Ping check** — pings Cloudflare `1.1.1.1` (fallback Quad9 `9.9.9.9`); privacy-friendly, avoids Google. Platform-aware timeout (`-W` in ms on macOS, seconds on Linux).
2. **Interface detection** — every 10s via `networksetup`/`ifconfig`/`ipconfig`
3. **VPN tunnel check** — every 5s, checks for `utun` interfaces via `scutil --nwi`. When tunnel drops, cached IP verification is invalidated immediately.
4. **VPN IP verification** — every 60s, hits `ipinfo.io/json` to empirically verify the public IP belongs to a known VPN provider (ASN org matching) or differs from the learned baseline ISP IP. Response data is sanitized (control chars stripped, truncated).
5. **VPN drop alert** — macOS notification with sound when VPN is not protecting (once per incident, resets on recovery). Distinguishes "tunnel up but IP unprotected" from "tunnel down".
6. **Safety kill** — kills Transmission.app when VPN is not verified
7. **Speed test** — periodic (default 5min) via `speedtest-cli` or curl fallback; runs in a background thread to avoid blocking the UI
8. **Render** — curses-based dashboard with uptime bars, interface list, VPN status. Uses cursor-home instead of clear to prevent flicker.

### Data Storage
SQLite at `~/.netbuoy/history.db` with two tables: `ping_log(ts, ok, latency_ms)` and `speed_log(ts, download_mbps, upload_mbps)`. Directory is chmod 700. Uptime is calculated over rolling windows (1min, 1hr, 1day, session, all-time).

### macOS System Interactions
All system commands use `subprocess.run` with timeouts. Key integrations:
- WiFi control: `networksetup -setairportpower en0 on/off`
- VPN tunnel detection: `scutil --nwi` for utun interfaces
- VPN IP verification: `ipinfo.io/json` — ASN org matched against `VPN_ORG_KEYWORDS` list + baseline IP comparison
- VPN drop notification: `osascript display notification` (no accessibility permissions needed)
- Process kill: `pgrep`/`osascript quit`/`killall` for Transmission.app

## Key Design Decisions

- **Privacy-first ping targets**: Cloudflare 1.1.1.1 and Quad9 9.9.9.9 — never Google
- **Default WiFi off**: Turns off WiFi on start (override with `--keep-wifi`)
- **Dual VPN verification**: Fast local tunnel check (utun, every 5s) + periodic empirical IP verification via `ipinfo.io/json` (every 60s). Safety actions trust verified status over tunnel status. Tunnel drop invalidates cached verification immediately.
- **VPN-first security**: Kills Transmission.app when VPN is not verified to prevent data leakage
- **Notification over auto-reconnect**: macOS accessibility API limitations prevent reliable programmatic VPN reconnection. We alert the user instead.
- **No heavy dependencies**: Python version uses mostly stdlib; only `speedtest-cli` is optional
- **Threaded speed tests**: Speed tests run in daemon threads to prevent UI freezing during 30s+ measurements
- **Flicker-free display**: Shell version uses `tput cup 0 0` + `tput el` instead of `clear`

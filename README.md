# netbuoy

[![Tests](https://github.com/kristovatlas/netbuoy/actions/workflows/tests.yml/badge.svg)](https://github.com/kristovatlas/netbuoy/actions/workflows/tests.yml)
[![Coverage](https://img.shields.io/badge/coverage-43%25-yellow)](https://github.com/kristovatlas/netbuoy)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)](https://github.com/kristovatlas/netbuoy)
[![License](https://img.shields.io/github/license/kristovatlas/netbuoy)](https://github.com/kristovatlas/netbuoy/blob/main/LICENSE)

Real-time network connectivity monitor and healer for macOS. Tracks uptime, manages VPN connections (Proton VPN), and protects against data leakage.

## Features

- **Connectivity monitoring** — Pings privacy-friendly targets (Cloudflare 1.1.1.1, Quad9 9.9.9.9) every 2 seconds
- **Uptime tracking** — Rolling windows (1min, 1hr, 1day, session, all-time) with SQLite-backed history
- **Dual VPN verification** — Fast local tunnel check + empirical IP verification via ipinfo.io ASN matching
- **VPN drop alert** — macOS notification with sound when VPN is down or tunnel is up but IP is unprotected
- **Safety kill** — Kills Transmission.app when VPN is not verified to prevent data leakage
- **WiFi management** — Turns off WiFi by default (Ethernet-first)
- **Speed tests** — Periodic bandwidth measurement via speedtest-cli or Cloudflare fallback
- **Curses dashboard** — Real-time terminal UI with color-coded status bars
- **Shell version** — Dependency-free `netbuoy.sh` for restricted environments

## Install

```bash
make install        # Python version → ~/.local/bin/netbuoy
make install-sh     # Shell-only version (no dependencies)
make uninstall
```

Make sure `~/.local/bin` is in your `PATH`. Add to your shell profile if needed:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Usage

```bash
netbuoy                          # Default: WiFi off, VPN managed, Transmission guarded
netbuoy --keep-wifi              # Leave WiFi on
netbuoy --no-vpn                 # Disable VPN monitoring
netbuoy --no-kill                # Don't kill Transmission
netbuoy --interval 1             # Ping every second
netbuoy --speed-interval 10      # Speed test every 10 minutes
netbuoy --ping-target 9.9.9.9    # Custom ping target
```

## Testing

```bash
python3 -m pytest tests/ -v              # Run all 113 tests
python3 -m pytest tests/ --cov=netbuoy   # With coverage report
bash -n netbuoy.sh                       # Shell syntax check
```

See [TESTING.md](TESTING.md) for the full testing plan including manual macOS integration tests.

## Architecture

```
netbuoy.py     Python CLI: curses UI, SQLite history, dual VPN verification, speed tests
netbuoy.sh     Shell CLI: ANSI display, session-only stats, same VPN/WiFi/kill features
Makefile       install / install-sh / uninstall
```

Data is stored in `~/.netbuoy/history.db` (SQLite with WAL).

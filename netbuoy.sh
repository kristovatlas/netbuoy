#!/bin/bash
# netbuoy (shell version) - Network connectivity monitor & healer for macOS
# Minimal version with no dependencies beyond standard macOS tools.
# No historical database or speed tests — session stats only.

set -euo pipefail
# Note: functions that intentionally return non-zero (ping_check, is_vpn_connected)
# must be called in conditional contexts (if/||) to avoid triggering set -e.

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

PING_TARGET="1.1.1.1"
FALLBACK_TARGET="9.9.9.9"
INTERVAL=2
KEEP_WIFI=false
NO_VPN=false
NO_KILL=false
VPN_VERIFY_INTERVAL=60
VPN_CHECK_URL="https://ipinfo.io/json"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Network connectivity monitor & healer for macOS (shell version).

Options:
  --keep-wifi          Don't turn off WiFi on start
  --ping-target HOST   Ping target (default: 1.1.1.1)
  --no-vpn             Disable VPN monitoring
  --no-kill            Don't kill Transmission.app when VPN is down
  --interval SEC       Ping interval in seconds (default: 2)
  -h, --help           Show this help
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep-wifi) KEEP_WIFI=true; shift ;;
        --ping-target) PING_TARGET="$2"; shift 2 ;;
        --no-vpn) NO_VPN=true; shift ;;
        --no-kill) NO_KILL=true; shift ;;
        --interval) INTERVAL="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

if [[ "$PING_TARGET" == -* ]]; then
    echo "Error: --ping-target must be a hostname or IP, not a flag" >&2
    exit 1
fi

if [[ "$INTERVAL" =~ ^-|^0$ ]]; then
    echo "Error: --interval must be positive" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

TOTAL_CHECKS=0
OK_CHECKS=0
SESSION_START=$(date +%s)
LAST_VPN_VERIFY=0
TRANSMISSION_KILLED=false
VPN_NOTIFIED=false
BASELINE_IP=""
VPN_TUNNEL=false
VPN_VERIFIED=""
VPN_IP=""
VPN_ORG=""

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

ping_check() {
    local target="$1"
    local output
    # macOS ping -W takes milliseconds
    output=$(ping -c 1 -W 2000 "$target" 2>/dev/null) || return 1
    LATENCY=$(echo "$output" | grep -oE 'time=[0-9.]+' | head -1 | cut -d= -f2)
    return 0
}

check_connectivity() {
    LATENCY=""
    if ping_check "$PING_TARGET"; then
        CONNECTED=true
    elif [ "$PING_TARGET" != "$FALLBACK_TARGET" ] && ping_check "$FALLBACK_TARGET"; then
        CONNECTED=true
    else
        CONNECTED=false
        LATENCY=""
    fi
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    if [ "$CONNECTED" = true ]; then
        OK_CHECKS=$((OK_CHECKS + 1))
    fi
}

is_wifi_on() {
    networksetup -getairportpower en0 2>/dev/null | grep -qi "on"
}

set_wifi() {
    networksetup -setairportpower en0 "$1" 2>/dev/null || true
}

is_vpn_connected() {
    # Check for utun interfaces via scutil
    if scutil --nwi 2>/dev/null | grep -q "utun"; then
        return 0
    fi
    # Fallback: check ifconfig for utun with inet
    if ifconfig 2>/dev/null | grep -A 5 "^utun" | grep -q "inet "; then
        return 0
    fi
    return 1
}

verify_vpn_ip() {
    # Fetch public IP info and check if org matches known VPN providers
    local json=""
    if command -v curl >/dev/null 2>&1; then
        json=$(curl -sS --max-time 10 -H "Accept: application/json" "$VPN_CHECK_URL" 2>/dev/null) || return 1
    elif command -v wget >/dev/null 2>&1; then
        json=$(wget -q -O - --timeout=10 --header="Accept: application/json" "$VPN_CHECK_URL" 2>/dev/null) || return 1
    else
        return 1
    fi

    # Parse IP and org (works without jq using grep/sed)
    VPN_IP=$(echo "$json" | grep -oE '"ip"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"ip"[[:space:]]*:[[:space:]]*"//;s/"//')
    VPN_ORG=$(echo "$json" | grep -oE '"org"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"org"[[:space:]]*:[[:space:]]*"//;s/"//')

    local org_lower
    org_lower=$(echo "$VPN_ORG" | tr '[:upper:]' '[:lower:]')

    # Check against known VPN provider keywords (synced with netbuoy.py VPN_ORG_KEYWORDS)
    VPN_VERIFIED=false
    local kw
    for kw in proton protonvpn "proton ag" nordvpn "nord security" mullvad expressvpn surfshark \
              "private internet access" pia cyberghost ivpn windscribe torguard airvpn "hide.me" \
              astrill purevpn ipvanish "hotspot shield" tunnelbear "mozilla vpn" wireguard \
              datacamp m247 hostinger leaseweb; do
        if echo "$org_lower" | grep -qF "$kw"; then
            VPN_VERIFIED=true
            break
        fi
    done

    # Also check if IP differs from baseline (ISP) IP
    if [ "$VPN_VERIFIED" = false ] && [ -n "$BASELINE_IP" ] && [ "$VPN_IP" != "$BASELINE_IP" ]; then
        VPN_VERIFIED=true
    fi

    # Learn baseline IP when tunnel is down
    if [ "$VPN_TUNNEL" = false ] && [ -z "$BASELINE_IP" ] && [ -n "$VPN_IP" ]; then
        BASELINE_IP="$VPN_IP"
    fi

    return 0
}

notify_vpn_unprotected() {
    local tunnel_up="$1"
    if [ "$VPN_NOTIFIED" = true ]; then
        return
    fi
    VPN_NOTIFIED=true
    local msg
    if [ "$tunnel_up" = true ]; then
        msg="VPN tunnel is up but your IP is NOT protected — reconnect in Proton VPN"
    else
        msg="VPN is down — reconnect in Proton VPN"
    fi
    osascript -e "display notification \"$msg\" with title \"netbuoy\" sound name \"Basso\"" 2>/dev/null || true
}

kill_transmission() {
    if pgrep -x Transmission >/dev/null 2>&1; then
        osascript -e 'tell application "Transmission" to quit' 2>/dev/null || true
        sleep 1
        if pgrep -x Transmission >/dev/null 2>&1; then
            killall Transmission 2>/dev/null || true
        fi
    fi
}

get_interfaces() {
    IFACE_INFO=""
    local ports
    ports=$(networksetup -listallhardwareports 2>/dev/null) || return
    local port="" device=""
    while IFS= read -r line; do
        if [[ "$line" == "Hardware Port:"* ]]; then
            port="${line#Hardware Port: }"
        elif [[ "$line" == "Device:"* ]]; then
            device="${line#Device: }"
            local ip=""
            ip=$(ipconfig getifaddr "$device" 2>/dev/null) || ip=""
            local active="○"
            if ifconfig "$device" 2>/dev/null | grep -q "status: active"; then
                active="●"
            fi
            if [ -n "$ip" ]; then
                IFACE_INFO="${IFACE_INFO}  ${active} ${port} (${device}): ${ip}\n"
            elif [ "$active" = "●" ]; then
                IFACE_INFO="${IFACE_INFO}  ${active} ${port} (${device}): no IP\n"
            fi
        fi
    done <<< "$ports"
}

format_duration() {
    local secs=$1
    if [ "$secs" -lt 60 ]; then
        echo "${secs}s"
    elif [ "$secs" -lt 3600 ]; then
        echo "$((secs / 60))m $((secs % 60))s"
    else
        echo "$((secs / 3600))h $(( (secs % 3600) / 60 ))m"
    fi
}

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

render() {
    # Move cursor to top-left instead of clearing — eliminates flicker
    tput cup 0 0 2>/dev/null || printf "\033[H"
    local el
    el=$(tput el 2>/dev/null) || el=$'\033[K'  # clear to end of line

    local now
    now=$(date +%s)
    local runtime=$((now - SESSION_START))

    # Header
    printf "\033[1;7m NETBUOY \033[0m \033[2mNetwork Monitor  uptime: %s\033[0m%s\n" "$(format_duration $runtime)" "$el"
    printf "%s\n" "$el"

    # Connection status
    if [ "$CONNECTED" = true ]; then
        printf "\033[1;42;37m CONNECTED \033[0m"
        [ -n "$LATENCY" ] && printf " \033[32m%sms\033[0m" "$LATENCY"
        printf "%s\n" "$el"
    else
        printf "\033[1;41;37m DISCONNECTED \033[0m%s\n" "$el"
    fi

    # VPN status
    if [ "$NO_VPN" = false ]; then
        # Tunnel status
        if [ "$VPN_TUNNEL" = true ]; then
            printf "\033[1;42;37m TUNNEL \033[0m \033[32mUp\033[0m%s\n" "$el"
        else
            printf "\033[1;41;37m TUNNEL \033[0m \033[1;31mDown\033[0m%s\n" "$el"
        fi
        # IP verification status
        if [ -z "$VPN_VERIFIED" ]; then
            printf "\033[1;43;30m VPN IP \033[0m \033[33mChecking...\033[0m%s\n" "$el"
        elif [ "$VPN_VERIFIED" = true ]; then
            printf "\033[1;42;37m VPN IP \033[0m \033[32mVerified  %s  (%s)\033[0m%s\n" "$VPN_IP" "$VPN_ORG" "$el"
        else
            printf "\033[1;41;37m VPN IP \033[0m \033[1;31mNOT Protected  (%s)\033[0m%s\n" "$VPN_ORG" "$el"
        fi
    fi
    printf "%s\n" "$el"

    # Session uptime
    local pct="--"
    if [ "$TOTAL_CHECKS" -gt 0 ]; then
        pct=$(awk "BEGIN { printf \"%.1f\", ($OK_CHECKS / $TOTAL_CHECKS) * 100 }")
    fi
    printf "\033[1;4mUptime (session):\033[0m%s\n" "$el"
    printf "  %s%% (%d/%d checks)%s\n" "$pct" "$OK_CHECKS" "$TOTAL_CHECKS" "$el"
    printf "%s\n" "$el"

    # Interfaces
    get_interfaces
    if [ -n "$IFACE_INFO" ]; then
        printf "\033[1;4mInterfaces:\033[0m%s\n" "$el"
        # Print each interface line with clear-to-eol
        while IFS= read -r iface_line; do
            [ -n "$iface_line" ] && printf "%s%s\n" "$iface_line" "$el"
        done <<< "$(printf "%b" "$IFACE_INFO")"
        printf "%s\n" "$el"
    fi

    # Footer
    printf "\033[2mq: quit  |  ping: %s  |  Ctrl+C to exit\033[0m%s\n" "$PING_TARGET" "$el"

    # Clear any leftover lines from a previous longer render (e.g. interfaces disappeared)
    local i
    for i in 1 2 3; do
        printf "%s\n" "$el"
    done
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# macOS check
if [ "$(uname -s)" != "Darwin" ]; then
    echo "Warning: netbuoy is designed for macOS. Some features may not work." >&2
fi

# Turn off WiFi by default
if [ "$KEEP_WIFI" = false ] && is_wifi_on; then
    set_wifi off
fi

# Trap cleanup
cleanup() {
    # Restore terminal
    tput cnorm 2>/dev/null || true
    echo ""
    echo "netbuoy stopped. Session: $OK_CHECKS/$TOTAL_CHECKS checks passed."
    exit 0
}
trap cleanup INT TERM

# Hide cursor and clear screen once at startup
tput civis 2>/dev/null || true
clear

while true; do
    check_connectivity

    # VPN management
    if [ "$NO_VPN" = false ]; then
        # Fast local tunnel check
        if is_vpn_connected; then
            VPN_TUNNEL=true
        else
            VPN_TUNNEL=false
            # Tunnel dropped — invalidate stale IP verification so we react immediately
            VPN_VERIFIED=""
        fi

        # Periodic IP verification
        local_now=$(date +%s)
        if [ "$CONNECTED" = true ] && [ $((local_now - LAST_VPN_VERIFY)) -ge "$VPN_VERIFY_INTERVAL" ]; then
            verify_vpn_ip || true
            LAST_VPN_VERIFY=$local_now
        fi

        # Decide if VPN is truly protecting us
        vpn_protecting=false
        if [ -n "$VPN_VERIFIED" ]; then
            vpn_protecting="$VPN_VERIFIED"
        else
            vpn_protecting="$VPN_TUNNEL"
        fi

        if [ "$vpn_protecting" = false ]; then
            # Kill Transmission if VPN is not protecting
            if [ "$NO_KILL" = false ] && [ "$TRANSMISSION_KILLED" = false ]; then
                kill_transmission
                TRANSMISSION_KILLED=true
            fi
            # Notify user (once per incident)
            notify_vpn_unprotected "$VPN_TUNNEL"
        else
            TRANSMISSION_KILLED=false
            VPN_NOTIFIED=false
        fi
    fi

    render

    # Check for 'q' key (non-blocking read)
    if read -rsn1 -t "$INTERVAL" key 2>/dev/null; then
        if [ "$key" = "q" ]; then
            cleanup
        fi
    fi
done

"""Tests for network interface detection, WiFi, and VPN tunnel checks.

All subprocess calls are mocked — these tests run on any platform.
"""
import subprocess
from pathlib import Path
from unittest import mock

import pytest

import netbuoy


class TestGetInterfaces:
    SAMPLE_PORTS = """Hardware Port: Ethernet
Device: en0

Hardware Port: Wi-Fi
Device: en1

Hardware Port: Thunderbolt Bridge
Device: bridge0"""

    def test_parses_hardware_ports(self):
        ports_result = mock.Mock(stdout=self.SAMPLE_PORTS, returncode=0)

        def mock_run(cmd, **kwargs):
            if cmd[0] == "networksetup":
                return ports_result
            elif cmd[0] == "ipconfig":
                device = cmd[2]
                if device == "en0":
                    return mock.Mock(stdout="192.168.1.100\n", returncode=0)
                return mock.Mock(stdout="", returncode=1)
            elif cmd[0] == "ifconfig":
                device = cmd[1]
                if device == "en0":
                    return mock.Mock(stdout="status: active\n", returncode=0)
                return mock.Mock(stdout="status: inactive\n", returncode=0)
            return mock.Mock(stdout="", returncode=1)

        with mock.patch("subprocess.run", side_effect=mock_run):
            interfaces = netbuoy.get_interfaces()

        assert len(interfaces) == 3
        eth = next(i for i in interfaces if i["device"] == "en0")
        assert eth["port"] == "Ethernet"
        assert eth["ip"] == "192.168.1.100"
        assert eth["active"] is True

        wifi = next(i for i in interfaces if i["device"] == "en1")
        assert wifi["ip"] is None
        assert wifi["active"] is False

    def test_networksetup_not_found(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            interfaces = netbuoy.get_interfaces()
        assert interfaces == []

    def test_networksetup_timeout(self):
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            interfaces = netbuoy.get_interfaces()
        assert interfaces == []


class TestWifi:
    def test_wifi_on(self):
        result = mock.Mock(stdout="Wi-Fi Power (en0): On", returncode=0)
        with mock.patch("subprocess.run", return_value=result):
            assert netbuoy.is_wifi_on() is True

    def test_wifi_off(self):
        result = mock.Mock(stdout="Wi-Fi Power (en0): Off", returncode=0)
        with mock.patch("subprocess.run", return_value=result):
            assert netbuoy.is_wifi_on() is False

    def test_wifi_command_not_found(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            assert netbuoy.is_wifi_on() is False

    def test_set_wifi_off(self):
        with mock.patch("subprocess.run") as mock_run:
            netbuoy.set_wifi(False)
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "off" in cmd

    def test_set_wifi_on(self):
        with mock.patch("subprocess.run") as mock_run:
            netbuoy.set_wifi(True)
            cmd = mock_run.call_args[0][0]
            assert "on" in cmd

    def test_set_wifi_handles_error(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            netbuoy.set_wifi(False)  # Should not raise


class TestIsVpnConnected:
    def test_detects_utun_via_scutil(self):
        scutil_output = """Network information

IPv4 network interface information
     en0 : flags      : 0x5 (IPv4,DNS)
           address     : 192.168.1.100
     utun3 : flags    : 0x5 (IPv4,DNS)
           address     : 10.2.0.1
"""
        result = mock.Mock(stdout=scutil_output, returncode=0)
        with mock.patch("subprocess.run", return_value=result):
            assert netbuoy.is_vpn_connected() is True

    def test_no_utun_via_scutil(self):
        scutil_output = """Network information

IPv4 network interface information
     en0 : flags      : 0x5 (IPv4,DNS)
           address     : 192.168.1.100
"""
        scutil_result = mock.Mock(stdout=scutil_output, returncode=0)
        ifconfig_output = """en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 192.168.1.100 netmask 0xffffff00 broadcast 192.168.1.255
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
"""
        ifconfig_result = mock.Mock(stdout=ifconfig_output, returncode=0)

        call_count = [0]

        def mock_run(cmd, **kwargs):
            if cmd[0] == "scutil":
                return scutil_result
            return ifconfig_result

        with mock.patch("subprocess.run", side_effect=mock_run):
            assert netbuoy.is_vpn_connected() is False

    def test_detects_utun_via_ifconfig_fallback(self):
        scutil_result = mock.Mock(stdout="no tunnel here", returncode=0)
        ifconfig_output = """en0: flags=8863<UP> mtu 1500
\tinet 192.168.1.100 netmask 0xffffff00
utun3: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380
\tinet 10.2.0.2 --> 10.2.0.2 netmask 0xffffffff
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
"""
        ifconfig_result = mock.Mock(stdout=ifconfig_output, returncode=0)

        def mock_run(cmd, **kwargs):
            if cmd[0] == "scutil":
                return scutil_result
            return ifconfig_result

        with mock.patch("subprocess.run", side_effect=mock_run):
            assert netbuoy.is_vpn_connected() is True

    def test_utun_without_inet_not_detected(self):
        scutil_result = mock.Mock(stdout="no tunnel here", returncode=0)
        ifconfig_output = (
            "utun0: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380\n"
            "lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384\n"
            "\tinet 127.0.0.1 netmask 0xff000000\n"
        )
        ifconfig_result = mock.Mock(stdout=ifconfig_output, returncode=0)

        def mock_run(cmd, **kwargs):
            if cmd[0] == "scutil":
                return scutil_result
            return ifconfig_result

        with mock.patch("subprocess.run", side_effect=mock_run):
            assert netbuoy.is_vpn_connected() is False

    def test_both_commands_fail(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            assert netbuoy.is_vpn_connected() is False

    def test_scutil_timeout_falls_back_to_ifconfig(self):
        call_count = [0]

        def mock_run(cmd, **kwargs):
            if cmd[0] == "scutil":
                raise subprocess.TimeoutExpired("scutil", 5)
            return mock.Mock(
                stdout="utun3: flags=8051<UP>\n\tinet 10.2.0.1 netmask 0xffffffff\n",
                returncode=0,
            )

        with mock.patch("subprocess.run", side_effect=mock_run):
            assert netbuoy.is_vpn_connected() is True


class TestRecycleVpn:
    def test_calls_open_with_helper_app(self, tmp_path):
        helper = tmp_path / "NetbuoyVPNHelper.app"
        helper.mkdir()
        with mock.patch.object(netbuoy, "VPN_HELPER_APP", helper), \
             mock.patch("subprocess.run") as mock_run:
            netbuoy.recycle_vpn()
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "open"
            assert cmd[1] == "-W"
            assert "NetbuoyVPNHelper.app" in cmd[2]

    def test_skips_when_helper_missing(self):
        with mock.patch.object(netbuoy, "VPN_HELPER_APP", Path("/nonexistent/app")), \
             mock.patch("subprocess.run") as mock_run:
            netbuoy.recycle_vpn()
            mock_run.assert_not_called()

    def test_handles_helper_not_found(self, tmp_path):
        helper = tmp_path / "NetbuoyVPNHelper.app"
        helper.mkdir()
        with mock.patch.object(netbuoy, "VPN_HELPER_APP", helper), \
             mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            netbuoy.recycle_vpn()  # Should not raise

    def test_handles_timeout(self, tmp_path):
        helper = tmp_path / "NetbuoyVPNHelper.app"
        helper.mkdir()
        with mock.patch.object(netbuoy, "VPN_HELPER_APP", helper), \
             mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 15)):
            netbuoy.recycle_vpn()  # Should not raise


class TestKillTransmission:
    def test_kills_when_running(self):
        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0] == "pgrep":
                return mock.Mock(returncode=0)
            return mock.Mock(returncode=0)

        with mock.patch("subprocess.run", side_effect=mock_run), \
             mock.patch("time.sleep"):
            netbuoy.kill_transmission()

        # Should have called pgrep, osascript quit, pgrep again, killall
        assert any("pgrep" in str(c) for c in calls)
        assert any("osascript" in str(c) for c in calls)

    def test_no_killall_when_graceful_quit_succeeds(self):
        """After osascript quit, if pgrep says process is gone, skip killall."""
        calls = []
        pgrep_count = [0]

        def mock_run(cmd, **kwargs):
            calls.append(cmd[0] if isinstance(cmd, list) else cmd)
            if cmd[0] == "pgrep":
                pgrep_count[0] += 1
                if pgrep_count[0] == 1:
                    return mock.Mock(returncode=0)  # first: running
                return mock.Mock(returncode=1)  # second: gone after quit
            return mock.Mock(returncode=0)

        with mock.patch("subprocess.run", side_effect=mock_run), \
             mock.patch("time.sleep"):
            netbuoy.kill_transmission()

        assert "killall" not in calls

    def test_does_nothing_when_not_running(self):
        result = mock.Mock(returncode=1)  # pgrep returns 1 = not found
        with mock.patch("subprocess.run", return_value=result) as mock_run:
            netbuoy.kill_transmission()
        # Only pgrep should be called
        assert mock_run.call_count == 1

    def test_handles_errors(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            netbuoy.kill_transmission()  # Should not raise

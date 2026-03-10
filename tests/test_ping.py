import re
import subprocess
from unittest import mock

import pytest

import netbuoy


class TestPingParsing:
    """Test the regex used to parse ping latency from output."""

    def _extract_latency(self, stdout):
        """Use the same regex as ping_check()."""
        m = re.search(r"time[=<]\s*([\d.]+)\s*ms", stdout)
        return float(m.group(1)) if m else None

    def test_standard_macos_format(self):
        output = "64 bytes from 1.1.1.1: icmp_seq=0 ttl=55 time=12.345 ms"
        assert self._extract_latency(output) == 12.345

    def test_linux_format(self):
        output = "64 bytes from 1.1.1.1: icmp_seq=1 ttl=55 time=8.72 ms"
        assert self._extract_latency(output) == 8.72

    def test_less_than_1ms(self):
        output = "64 bytes from 127.0.0.1: icmp_seq=0 ttl=64 time<1 ms"
        assert self._extract_latency(output) == 1.0

    def test_integer_latency(self):
        output = "64 bytes from 1.1.1.1: icmp_seq=0 ttl=55 time=5 ms"
        assert self._extract_latency(output) == 5.0

    def test_no_time_field(self):
        output = "Request timeout for icmp_seq 0"
        assert self._extract_latency(output) is None

    def test_empty_output(self):
        assert self._extract_latency("") is None

    def test_multiline_output(self):
        output = """PING 1.1.1.1 (1.1.1.1): 56 data bytes
64 bytes from 1.1.1.1: icmp_seq=0 ttl=55 time=14.2 ms

--- 1.1.1.1 ping statistics ---
1 packets transmitted, 1 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 14.2/14.2/14.2/0.000 ms"""
        assert self._extract_latency(output) == 14.2


class TestPingCheck:
    def test_successful_ping(self):
        fake_result = mock.Mock()
        fake_result.returncode = 0
        fake_result.stdout = "64 bytes from 1.1.1.1: icmp_seq=0 ttl=55 time=12.3 ms"
        with mock.patch("subprocess.run", return_value=fake_result):
            ok, latency = netbuoy.ping_check("1.1.1.1")
        assert ok is True
        assert latency == 12.3

    def test_macos_uses_milliseconds_for_timeout(self):
        fake_result = mock.Mock(returncode=0, stdout="time=10.0 ms")
        with mock.patch("platform.system", return_value="Darwin"), \
             mock.patch("subprocess.run", return_value=fake_result) as mock_run:
            netbuoy.ping_check("1.1.1.1", timeout=2)
        cmd = mock_run.call_args[0][0]
        assert cmd[3] == "-W"
        assert cmd[4] == "2000"  # milliseconds

    def test_linux_uses_seconds_for_timeout(self):
        fake_result = mock.Mock(returncode=0, stdout="time=10.0 ms")
        with mock.patch("platform.system", return_value="Linux"), \
             mock.patch("subprocess.run", return_value=fake_result) as mock_run:
            netbuoy.ping_check("1.1.1.1", timeout=2)
        cmd = mock_run.call_args[0][0]
        assert cmd[3] == "-W"
        assert cmd[4] == "2"  # seconds

    def test_failed_ping(self):
        fake_result = mock.Mock()
        fake_result.returncode = 1
        fake_result.stdout = ""
        with mock.patch("subprocess.run", return_value=fake_result):
            ok, latency = netbuoy.ping_check("192.0.2.1")
        assert ok is False
        assert latency is None

    def test_timeout_returns_false(self):
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ping", 4)):
            ok, latency = netbuoy.ping_check("1.1.1.1")
        assert ok is False
        assert latency is None

    def test_command_not_found(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            ok, latency = netbuoy.ping_check("1.1.1.1")
        assert ok is False
        assert latency is None

    def test_success_but_no_time_in_output(self):
        fake_result = mock.Mock()
        fake_result.returncode = 0
        fake_result.stdout = "some unexpected output"
        with mock.patch("subprocess.run", return_value=fake_result):
            ok, latency = netbuoy.ping_check("1.1.1.1")
        assert ok is True
        assert latency is None

import pytest

import netbuoy


class TestFormatDuration:
    def test_seconds(self):
        assert netbuoy.format_duration(0) == "0s"
        assert netbuoy.format_duration(1) == "1s"
        assert netbuoy.format_duration(45) == "45s"
        assert netbuoy.format_duration(59) == "59s"

    def test_minutes(self):
        assert netbuoy.format_duration(60) == "1m 0s"
        assert netbuoy.format_duration(90) == "1m 30s"
        assert netbuoy.format_duration(3599) == "59m 59s"

    def test_hours(self):
        assert netbuoy.format_duration(3600) == "1h 0m"
        assert netbuoy.format_duration(3661) == "1h 1m"
        assert netbuoy.format_duration(7200) == "2h 0m"
        assert netbuoy.format_duration(86400) == "24h 0m"

    def test_float_input(self):
        assert netbuoy.format_duration(45.7) == "45s"
        assert netbuoy.format_duration(90.9) == "1m 30s"


class TestFormatUptime:
    def test_none_returns_placeholder(self):
        assert netbuoy.format_uptime(None) == "  --  "

    def test_100_percent(self):
        assert netbuoy.format_uptime(100.0) == "100.0%"

    def test_0_percent(self):
        assert netbuoy.format_uptime(0.0) == "  0.0%"

    def test_decimal(self):
        assert netbuoy.format_uptime(99.5) == " 99.5%"

    def test_low_value(self):
        assert netbuoy.format_uptime(1.2) == "  1.2%"


class TestRedactState:
    def _make_state(self):
        return {
            "vpn_ip": "98.76.54.32",
            "vpn_org": "AS9009 M247 Europe SRL",
            "interfaces": [
                {"port": "USB 10/100/1000 LAN", "device": "en7", "ip": "10.0.0.5", "active": True},
            ],
            "connected": True,
            "latency": 12.3,
        }

    def test_replaces_vpn_ip(self):
        s = netbuoy.redact_state(self._make_state())
        assert s["vpn_ip"] == "203.0.113.42"

    def test_replaces_vpn_org(self):
        s = netbuoy.redact_state(self._make_state())
        assert s["vpn_org"] == "AS12345 Acme VPN Provider"

    def test_replaces_interfaces(self):
        s = netbuoy.redact_state(self._make_state())
        assert s["interfaces"] == netbuoy.DEMO_INTERFACES

    def test_preserves_other_fields(self):
        s = netbuoy.redact_state(self._make_state())
        assert s["connected"] is True
        assert s["latency"] == 12.3

    def test_does_not_mutate_original(self):
        original = self._make_state()
        netbuoy.redact_state(original)
        assert original["vpn_ip"] == "98.76.54.32"

    def test_handles_empty_vpn_ip(self):
        state = self._make_state()
        state["vpn_ip"] = ""
        s = netbuoy.redact_state(state)
        assert s["vpn_ip"] == ""

    def test_handles_none_vpn_org(self):
        state = self._make_state()
        state["vpn_org"] = None
        s = netbuoy.redact_state(state)
        assert s["vpn_org"] is None

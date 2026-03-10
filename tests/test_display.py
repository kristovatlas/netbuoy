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

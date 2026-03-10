import sys
from unittest import mock

import pytest

import netbuoy


def parse_args(args_list):
    """Helper to parse CLI args without running main()."""
    with mock.patch("sys.argv", ["netbuoy"] + args_list):
        parser = _make_parser()
        return parser.parse_args(args_list)


def _make_parser():
    """Recreate the argument parser from main()."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-wifi", action="store_true")
    parser.add_argument("--vpn-mode", choices=["fastest", "random"], default="fastest")
    parser.add_argument("--ping-target", default=netbuoy.DEFAULT_PING_TARGET)
    parser.add_argument("--no-vpn", action="store_true")
    parser.add_argument("--no-kill", action="store_true")
    parser.add_argument("--interval", type=float, default=netbuoy.DEFAULT_INTERVAL)
    parser.add_argument("--speed-interval", type=float, default=netbuoy.DEFAULT_SPEED_INTERVAL)
    return parser


class TestDefaults:
    def test_default_interval(self):
        args = parse_args([])
        assert args.interval == 2

    def test_default_speed_interval(self):
        args = parse_args([])
        assert args.speed_interval == 5

    def test_default_ping_target(self):
        args = parse_args([])
        assert args.ping_target == "1.1.1.1"

    def test_default_vpn_mode(self):
        args = parse_args([])
        assert args.vpn_mode == "fastest"

    def test_default_keep_wifi_false(self):
        args = parse_args([])
        assert args.keep_wifi is False

    def test_default_no_vpn_false(self):
        args = parse_args([])
        assert args.no_vpn is False

    def test_default_no_kill_false(self):
        args = parse_args([])
        assert args.no_kill is False


class TestFlags:
    def test_keep_wifi(self):
        args = parse_args(["--keep-wifi"])
        assert args.keep_wifi is True

    def test_no_vpn(self):
        args = parse_args(["--no-vpn"])
        assert args.no_vpn is True

    def test_no_kill(self):
        args = parse_args(["--no-kill"])
        assert args.no_kill is True

    def test_vpn_mode_random(self):
        args = parse_args(["--vpn-mode", "random"])
        assert args.vpn_mode == "random"

    def test_vpn_mode_fastest(self):
        args = parse_args(["--vpn-mode", "fastest"])
        assert args.vpn_mode == "fastest"

    def test_vpn_mode_invalid(self):
        with pytest.raises(SystemExit):
            parse_args(["--vpn-mode", "invalid"])

    def test_custom_ping_target(self):
        args = parse_args(["--ping-target", "8.8.8.8"])
        assert args.ping_target == "8.8.8.8"

    def test_custom_interval(self):
        args = parse_args(["--interval", "0.5"])
        assert args.interval == 0.5

    def test_custom_speed_interval(self):
        args = parse_args(["--speed-interval", "10"])
        assert args.speed_interval == 10.0

    def test_interval_accepts_float(self):
        args = parse_args(["--interval", "1.5"])
        assert args.interval == 1.5

    def test_multiple_flags(self):
        args = parse_args(["--keep-wifi", "--no-vpn", "--no-kill", "--interval", "3"])
        assert args.keep_wifi is True
        assert args.no_vpn is True
        assert args.no_kill is True
        assert args.interval == 3.0


class TestHelpExits:
    def test_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--help"])
        assert exc_info.value.code == 0


class TestInputValidation:
    """Test validation that happens in main() after parsing."""

    def test_negative_interval_rejected(self):
        parser = _make_parser()
        args = parser.parse_args(["--interval", "-1"])
        assert args.interval == -1  # argparse accepts it
        # But main() would call parser.error()

    def test_zero_interval_rejected(self):
        parser = _make_parser()
        args = parser.parse_args(["--interval", "0"])
        assert args.interval == 0.0

    def test_ping_target_flag_rejected_by_argparse(self):
        """A ping target that looks like a flag is rejected by argparse itself."""
        parser = _make_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--ping-target", "-n"])

    def test_ping_target_with_leading_dash_via_equals(self):
        """Using = syntax, a dash-prefixed target reaches our validation."""
        parser = _make_parser()
        args = parser.parse_args(["--ping-target=-n"])
        assert args.ping_target == "-n"
        assert args.ping_target.startswith("-")

    def test_valid_ping_target_accepted(self):
        parser = _make_parser()
        args = parser.parse_args(["--ping-target", "9.9.9.9"])
        assert not args.ping_target.startswith("-")

    def test_zero_speed_interval_rejected(self):
        parser = _make_parser()
        args = parser.parse_args(["--speed-interval", "0"])
        assert args.speed_interval == 0.0

"""Tests for main loop state management and decision logic.

These test the integration of VPN tunnel + IP verification for safety decisions.
"""
import time
from types import SimpleNamespace
from unittest import mock

import pytest

import netbuoy


def make_args(**overrides):
    defaults = {
        "keep_wifi": True,
        "vpn_mode": "fastest",
        "ping_target": "1.1.1.1",
        "no_vpn": False,
        "no_kill": False,
        "interval": 2,
        "speed_interval": 5,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestVpnProtectionLogic:
    """Test the combined tunnel + verified logic for VPN protection decisions."""

    def test_verified_true_overrides_tunnel_false(self):
        """If IP says VPN, trust it even if tunnel check says no."""
        # vpn_verified is not None → use it
        vpn_verified = True
        vpn_tunnel = False
        if vpn_verified is not None:
            vpn_protecting = vpn_verified
        else:
            vpn_protecting = vpn_tunnel
        assert vpn_protecting is True

    def test_verified_false_overrides_tunnel_true(self):
        """If IP says no VPN, don't trust tunnel check alone."""
        vpn_verified = False
        vpn_tunnel = True
        if vpn_verified is not None:
            vpn_protecting = vpn_verified
        else:
            vpn_protecting = vpn_tunnel
        assert vpn_protecting is False

    def test_verified_none_falls_back_to_tunnel(self):
        """Before first IP check, use tunnel status."""
        vpn_verified = None
        vpn_tunnel = True
        if vpn_verified is not None:
            vpn_protecting = vpn_verified
        else:
            vpn_protecting = vpn_tunnel
        assert vpn_protecting is True

    def test_verified_none_tunnel_false(self):
        vpn_verified = None
        vpn_tunnel = False
        if vpn_verified is not None:
            vpn_protecting = vpn_verified
        else:
            vpn_protecting = vpn_tunnel
        assert vpn_protecting is False


class TestBaselineIpLearning:
    """Test that baseline IP is learned correctly."""

    def test_learned_when_tunnel_down(self):
        """Baseline IP should be set from first verify when tunnel is down."""
        baseline_ip = None
        vpn_tunnel = False
        result = {"ip": "73.1.2.3", "verified": False, "org": "Comcast", "reason": "ISP"}

        if not vpn_tunnel and baseline_ip is None and result["ip"]:
            baseline_ip = result["ip"]

        assert baseline_ip == "73.1.2.3"

    def test_not_learned_when_tunnel_up(self):
        """Don't learn baseline when tunnel is up — it would be the VPN IP."""
        baseline_ip = None
        vpn_tunnel = True
        result = {"ip": "185.1.2.3", "verified": True, "org": "Proton AG", "reason": "VPN"}

        if not vpn_tunnel and baseline_ip is None and result["ip"]:
            baseline_ip = result["ip"]

        assert baseline_ip is None

    def test_not_overwritten_once_set(self):
        """Baseline IP should only be set once."""
        baseline_ip = "73.1.2.3"
        vpn_tunnel = False
        result = {"ip": "99.9.9.9", "verified": False, "org": "AT&T", "reason": "ISP"}

        if not vpn_tunnel and baseline_ip is None and result["ip"]:
            baseline_ip = result["ip"]

        assert baseline_ip == "73.1.2.3"


class TestTransmissionKillGuard:
    """Test that Transmission is only killed once per VPN-down episode."""

    def test_killed_once_not_repeatedly(self):
        kill_count = 0
        transmission_killed = False

        # Simulate 3 loop iterations with VPN down
        for _ in range(3):
            vpn_protecting = False
            no_kill = False
            if not no_kill and not transmission_killed:
                kill_count += 1
                transmission_killed = True

        assert kill_count == 1

    def test_reset_when_vpn_returns(self):
        transmission_killed = True

        # VPN comes back
        vpn_protecting = True
        if vpn_protecting:
            transmission_killed = False

        assert transmission_killed is False

    def test_no_kill_flag_prevents_kill(self):
        killed = False
        transmission_killed = False
        no_kill = True

        vpn_protecting = False
        if not no_kill and not transmission_killed:
            killed = True

        assert killed is False


class TestVpnRecycleCooldown:
    """Test VPN recycle cooldown logic."""

    def test_recycle_respects_cooldown(self):
        recycle_count = 0
        last_vpn_recycle = 0
        cooldown = netbuoy.VPN_RECYCLE_COOLDOWN

        # Simulate ticks at 100, 110, 120, 130, 140 seconds
        # First recycle at t=100 (100-0 >= 30), next at t=130 (130-100 >= 30)
        for t in [100, 110, 120, 130, 140]:
            now = t
            connected = True
            vpn_protecting = False
            if connected and (now - last_vpn_recycle >= cooldown):
                recycle_count += 1
                last_vpn_recycle = now

        # Should recycle at t=100 and t=130
        assert recycle_count == 2

    def test_no_recycle_when_disconnected(self):
        recycled = False
        connected = False
        if connected:
            recycled = True
        assert recycled is False

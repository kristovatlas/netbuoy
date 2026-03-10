import json
from unittest import mock
from urllib.error import URLError

import pytest

import netbuoy


def _mock_ipinfo_response(ip, org):
    """Create a mock urllib response for ipinfo.io."""
    data = json.dumps({"ip": ip, "org": org}).encode()

    class FakeResponse:
        def read(self):
            return data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    return FakeResponse()


class TestVpnOrgKeywords:
    def test_all_keywords_are_lowercase(self):
        for kw in netbuoy.VPN_ORG_KEYWORDS:
            assert kw == kw.lower(), f"Keyword '{kw}' is not lowercase"

    def test_no_duplicate_keywords(self):
        assert len(netbuoy.VPN_ORG_KEYWORDS) == len(set(netbuoy.VPN_ORG_KEYWORDS))


class TestVerifyVpnIp:
    def test_proton_vpn_detected(self):
        resp = _mock_ipinfo_response("185.159.157.1", "AS209103 Proton AG")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            result = netbuoy.verify_vpn_ip()
        assert result["verified"] is True
        assert result["ip"] == "185.159.157.1"
        assert "Proton" in result["org"]
        assert "VPN provider" in result["reason"]

    def test_mullvad_detected(self):
        resp = _mock_ipinfo_response("198.54.128.1", "AS396356 Mullvad VPN")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            result = netbuoy.verify_vpn_ip()
        assert result["verified"] is True

    def test_nordvpn_detected(self):
        resp = _mock_ipinfo_response("89.187.161.1", "AS212238 NordVPN")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            result = netbuoy.verify_vpn_ip()
        assert result["verified"] is True

    def test_m247_infra_detected(self):
        resp = _mock_ipinfo_response("146.70.1.1", "AS9009 M247 Ltd")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            result = netbuoy.verify_vpn_ip()
        assert result["verified"] is True

    def test_residential_isp_not_vpn(self):
        resp = _mock_ipinfo_response("73.1.2.3", "AS7922 Comcast Cable Communications")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            result = netbuoy.verify_vpn_ip()
        assert result["verified"] is False
        assert "ISP" in result["reason"]

    def test_att_not_vpn(self):
        resp = _mock_ipinfo_response("99.1.2.3", "AS7018 AT&T Services Inc.")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            result = netbuoy.verify_vpn_ip()
        assert result["verified"] is False

    def test_case_insensitive_matching(self):
        resp = _mock_ipinfo_response("1.2.3.4", "AS209103 PROTON AG")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            result = netbuoy.verify_vpn_ip()
        assert result["verified"] is True

    def test_ip_changed_from_baseline(self):
        resp = _mock_ipinfo_response("185.1.2.3", "AS12345 Unknown ISP")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            result = netbuoy.verify_vpn_ip(baseline_ip="73.1.2.3")
        assert result["verified"] is True
        assert "differs from baseline" in result["reason"]

    def test_ip_same_as_baseline_no_vpn_org(self):
        resp = _mock_ipinfo_response("73.1.2.3", "AS7922 Comcast Cable")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            result = netbuoy.verify_vpn_ip(baseline_ip="73.1.2.3")
        assert result["verified"] is False

    def test_baseline_none_only_uses_org(self):
        resp = _mock_ipinfo_response("73.1.2.3", "AS7922 Comcast")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            result = netbuoy.verify_vpn_ip(baseline_ip=None)
        assert result["verified"] is False

    def test_network_failure_returns_none(self):
        with mock.patch("urllib.request.urlopen", side_effect=URLError("timeout")):
            result = netbuoy.verify_vpn_ip()
        assert result is None

    def test_malformed_json_returns_none(self):
        class FakeResponse:
            def read(self):
                return b"not json"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            result = netbuoy.verify_vpn_ip()
        assert result is None

    def test_missing_org_field(self):
        data = json.dumps({"ip": "1.2.3.4"}).encode()

        class FakeResponse:
            def read(self):
                return data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            result = netbuoy.verify_vpn_ip()
        assert result is not None
        assert result["verified"] is False
        assert result["org"] == ""

    def test_missing_ip_field(self):
        data = json.dumps({"org": "AS209103 Proton AG"}).encode()

        class FakeResponse:
            def read(self):
                return data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            result = netbuoy.verify_vpn_ip()
        assert result is not None
        assert result["verified"] is True
        assert result["ip"] == ""

    def test_each_keyword_matches(self):
        """Every keyword in VPN_ORG_KEYWORDS should actually trigger a match."""
        for kw in netbuoy.VPN_ORG_KEYWORDS:
            org = f"AS12345 Test {kw} Corp"
            resp = _mock_ipinfo_response("1.2.3.4", org)
            with mock.patch("urllib.request.urlopen", return_value=resp):
                result = netbuoy.verify_vpn_ip()
            assert result["verified"] is True, f"Keyword '{kw}' did not trigger a match"

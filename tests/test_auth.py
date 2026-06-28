"""Small auth helper tests that do not touch browsers or the network."""

from types import SimpleNamespace

from twscrape_twitter_mcp.auth import _account_field, _cdp_port, _extract_creds


def test_account_field_handles_dicts_and_objects():
    assert _account_field({"active": True}, "active") is True
    assert _account_field(SimpleNamespace(active=False), "active") is False
    assert _account_field({}, "missing", "fallback") == "fallback"


def test_extract_creds_requires_auth_token_and_ct0():
    assert _extract_creds(
        [
            {"name": "auth_token", "value": "token"},
            {"name": "ct0", "value": "csrf"},
        ]
    ) == {"auth_token": "token", "ct0": "csrf"}
    assert _extract_creds([{"name": "auth_token", "value": "token"}]) is None


def test_cdp_port_defaults_and_parses_explicit_port():
    assert _cdp_port("http://127.0.0.1:9333") == 9333
    assert _cdp_port("http://127.0.0.1") == 9222

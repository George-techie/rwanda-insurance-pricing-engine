"""Contract tests for the CoverSoko integration, with the HTTP layer mocked so
they run offline. They verify the request we send, the normalization of the
response, tenant (ownerId) handling, error surfacing, and tool registration."""
import pytest

from assar.integrations import coversoko
from assar.pricing.registry import get_tool_schemas, run_tool

# A representative CoverSoko QuoteResult (rates are fractions; premium = SI*totalRate).
_CANNED = {
    "success": True,
    "message": "Premium calculated successfully",
    "data": {
        "baseRate": 0.0015,
        "specialPerilsRate": 0.0005,
        "totalRate": 0.0020,
        "premium": 20000.0,
        "breakdown": [
            {"label": "Banks", "rate": 0.0015},
            {"label": "Earthquake", "rate": 0.0003},
            {"label": "Riot & Strike", "rate": 0.0002},
        ],
    },
}


@pytest.fixture
def captured(monkeypatch):
    """Enable the backend and capture the outgoing request payload."""
    monkeypatch.setenv("COVERSOKO_API_URL", "http://coversoko.test")
    box = {}

    def fake_request(method, path, payload=None):
        box["method"], box["path"], box["payload"] = method, path, payload
        return _CANNED

    monkeypatch.setattr(coversoko, "_request", fake_request)
    return box


def test_enabled_follows_env(monkeypatch):
    monkeypatch.delenv("COVERSOKO_API_URL", raising=False)
    assert not coversoko.enabled()
    monkeypatch.setenv("COVERSOKO_API_URL", "http://x")
    assert coversoko.enabled()


def test_quote_builds_request_and_normalizes(captured):
    out = coversoko.quote(
        "Fire_Allied_Perils", 10_000_000, "standardFireRate",
        {"propertyType": "commercial", "propertyCategory": "Banks"},
        special_peril_names=["Earthquake", "Riot & Strike"],
    )
    # request shape
    assert captured["method"] == "POST" and captured["path"] == "/api/quote"
    p = captured["payload"]
    assert p["perilType"] == "Fire_Allied_Perils"
    assert p["sumInsured"] == 10_000_000
    assert p["coverType"] == "standardFireRate"
    assert p["attributes"]["propertyCategory"] == "Banks"
    assert p["specialPerilNames"] == ["Earthquake", "Riot & Strike"]
    # normalization: fractions shown as percent, premium passed through
    assert "error" not in out
    assert out["source"] == "coversoko"
    assert out["rate"] == 0.2          # 0.0020 -> 0.2%
    assert out["final_premium"] == 20000.0
    assert out["product"] == "Fire_Allied_Perils (standardFireRate)"


def test_owner_id_comes_from_env_not_model(captured, monkeypatch):
    monkeypatch.setenv("COVERSOKO_OWNER_ID", "insurer-uuid-123")
    coversoko.quote("Fire_Allied_Perils", 1_000_000, "standardFireRate",
                    {"propertyCategory": "Banks"})
    assert captured["payload"]["ownerId"] == "insurer-uuid-123"


def test_disabled_returns_error(monkeypatch):
    monkeypatch.delenv("COVERSOKO_API_URL", raising=False)
    out = coversoko.quote("Fire_Allied_Perils", 1_000_000, "standardFireRate", {})
    assert "error" in out


def test_unreachable_is_surfaced_not_raised(monkeypatch):
    monkeypatch.setenv("COVERSOKO_API_URL", "http://coversoko.test")

    def boom(*a, **k):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(coversoko, "_request", boom)
    out = coversoko.quote("Fire_Allied_Perils", 1_000_000, "standardFireRate", {})
    assert "error" in out and "unreachable" in out["error"].lower()


def test_tool_registered_only_when_enabled(monkeypatch):
    monkeypatch.delenv("COVERSOKO_API_URL", raising=False)
    names = [t["function"]["name"] for t in get_tool_schemas()]
    assert "quote_property" not in names
    monkeypatch.setenv("COVERSOKO_API_URL", "http://x")
    names = [t["function"]["name"] for t in get_tool_schemas()]
    assert "quote_property" in names


def test_run_tool_dispatches_to_coversoko(captured):
    # string number + string boolean, as a small model would emit them
    out = run_tool("quote_property", {
        "perilType": "Fire_Allied_Perils", "sumInsured": "10000000",
        "coverType": "standardFireRate",
        "attributes": {"propertyType": "commercial", "propertyCategory": "Banks"},
        "includeAllSpecialPerils": "true",
    })
    assert "error" not in out
    assert out["final_premium"] == 20000.0
    assert captured["payload"]["includeAllSpecialPerils"] is True
    assert captured["payload"]["sumInsured"] == 10000000

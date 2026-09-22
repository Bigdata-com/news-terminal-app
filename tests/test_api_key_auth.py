"""Inbound X-API-KEY auth: public vs protected routes, no env fallback."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import price_service


PROTECTED_GET: list[tuple[str, dict[str, str]]] = [
    ("/api/search/earnings", {}),
    ("/api/prices?tickers=AAPL", {}),
    ("/api/cache/stats", {}),
]

PROTECTED_POST: list[tuple[str, dict[str, Any]]] = [
    ("/api/news/AAPL", {"days": 7}),
    ("/api/news-multi", {"tickers": ["AAPL"], "days": 7}),
    ("/api/sector-news", {"sector": "energy", "days": 7}),
    ("/api/generate-commentary", {"ticker": "AAPL", "topic_results": []}),
    ("/api/cache/clear", {}),
]


@pytest.fixture
def client() -> Iterator[TestClient]:
    import main as app_module

    with TestClient(app_module.app) as test_client:
        yield test_client


def test_import_main_without_bigdata_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BIGDATA_API_KEY", raising=False)
    sys.modules.pop("main", None)
    app_module = importlib.import_module("main")
    assert app_module.app is not None
    assert not hasattr(app_module, "BIGDATA_API_KEY")


def test_public_routes_do_not_require_key(client: TestClient) -> None:
    for path in ("/api/config", "/api/health", "/api/sectors"):
        response = client.get(path)
        assert response.status_code == 200, path

    config = client.get("/api/config").json()
    assert config["bigdata_api_key_configured"] is False

    health = client.get("/api/health").json()
    assert health["api_key_configured"] is False


@pytest.mark.parametrize("path,params", PROTECTED_GET)
def test_protected_get_requires_key(
    client: TestClient,
    path: str,
    params: dict[str, str],
) -> None:
    response = client.get(path, params=params)
    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "API key required"
    assert "X-API-KEY" in body["message"]


@pytest.mark.parametrize("path,payload", PROTECTED_POST)
def test_protected_post_requires_key(
    client: TestClient,
    path: str,
    payload: dict[str, Any],
) -> None:
    response = client.post(path, json=payload)
    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "API key required"


def test_empty_header_is_rejected(client: TestClient) -> None:
    response = client.get("/api/cache/stats", headers={"X-API-KEY": "   "})
    assert response.status_code == 401


def test_news_uses_header_key_not_env(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    class FakeService:
        def __init__(self, api_key: str, base_url: str = "", **_kwargs: object) -> None:
            captured["api_key"] = api_key
            self.rate_limiter = type("RL", (), {"get_metrics": lambda self: {}})()

        async def close(self) -> None:
            return None

        async def search_ticker(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
            return {
                "ticker": "AAPL",
                "company_name": "Apple",
                "entity_id": "D8442A",
                "topic_results": [],
                "total_results": 0,
                "search_stats": {},
            }

    monkeypatch.setattr("main.TopicSearchService", FakeService)

    response = client.post(
        "/api/news/AAPL",
        json={"days": 7, "relevance": 0.1},
        headers={"X-API-KEY": "user-key-123"},
    )
    assert response.status_code == 200, response.text
    assert captured["api_key"] == "user-key-123"
    assert response.json()["ticker"] == "AAPL"


def test_cache_stats_accepts_header_key(client: TestClient) -> None:
    response = client.get("/api/cache/stats", headers={"X-API-KEY": "user-key-123"})
    assert response.status_code == 200
    assert "cache_stats" in response.json()


def test_price_service_requires_caller_key() -> None:
    with pytest.raises(ValueError, match="Bigdata API key is required"):
        price_service._get_api_key(None)
    with pytest.raises(ValueError, match="Bigdata API key is required"):
        price_service._get_api_key("  ")
    assert price_service._get_api_key("  abc  ") == "abc"

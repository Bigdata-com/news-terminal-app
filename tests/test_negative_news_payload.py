"""Unit tests for negative-news search payload construction."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.topic_search_service import TopicSearchService


class _FakeResponse:
    def __init__(self, status: int = 200, payload: dict[str, Any] | None = None) -> None:
        self.status = status
        self._payload = payload or {"results": []}

    async def json(self) -> dict[str, Any]:
        return self._payload

    async def text(self) -> str:
        return json.dumps(self._payload)

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_search_negative_category_payload_shape() -> None:
    """Outbound Bigdata search must match negative-news filter contract."""
    captured: dict[str, Any] = {}

    service = TopicSearchService(api_key="test-key", base_url="https://api.bigdata.com/v1")
    service.rate_limiter.acquire = AsyncMock()

    fake_session = MagicMock()

    def _post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _FakeResponse()

    fake_session.post = _post

    with patch.object(service, "_get_session", AsyncMock(return_value=fake_session)):
        await service.search_negative_category(
            entity_ids=["E09E2B"],
            entity_to_ticker={"E09E2B": "AAPL"},
            category={
                "category_name": "Credit stress",
                "topics": [
                    "business,bankruptcy,technical-default,fears,",
                    "business,credit,coupon-payment-failed,fears,",
                ],
            },
            category_index=0,
            days=30,
            max_chunks=10,
        )

    body = captured["json"]
    assert body["search_mode"] == "fast"
    query = body["query"]
    assert "text" not in query
    filters = query["filters"]
    assert filters["category"] == {"mode": "INCLUDE", "values": ["news_public", "transcripts"]}
    assert "document_type" not in filters
    assert filters["sentiment"] == {"ranges": [{"min": -1, "max": -0.1}]}
    assert "values" not in filters["sentiment"]
    assert filters["entity"]["search_in"] == "HEADLINE"
    assert filters["entity"]["any_of"] == ["E09E2B"]
    assert filters["topic"]["search_in"] == "ALL"
    assert "business,bankruptcy,technical-default,fears," in filters["topic"]["any_of"]
    assert query["max_chunks"] == 10

    await service.close()


@pytest.mark.asyncio
async def test_search_negative_category_truncates_to_single_entity() -> None:
    captured: dict[str, Any] = {}
    service = TopicSearchService(api_key="test-key", base_url="https://api.bigdata.com/v1")
    service.rate_limiter.acquire = AsyncMock()
    fake_session = MagicMock()

    def _post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["json"] = kwargs.get("json")
        return _FakeResponse()

    fake_session.post = _post
    entity_ids = [f"E{i}" for i in range(7)]
    entity_to_ticker = {eid: f"T{i}" for i, eid in enumerate(entity_ids)}

    with patch.object(service, "_get_session", AsyncMock(return_value=fake_session)):
        await service.search_negative_category(
            entity_ids=entity_ids,
            entity_to_ticker=entity_to_ticker,
            category={"category_name": "Regulatory", "topics": ["business,regulatory,regulatory-investigation,,"]},
            category_index=1,
            days=7,
            max_chunks=5,
        )

    assert captured["json"]["query"]["filters"]["entity"]["any_of"] == ["E0"]
    await service.close()


@pytest.mark.asyncio
async def test_custom_categories_override_defaults() -> None:
    service = TopicSearchService(api_key="test-key", base_url="https://api.bigdata.com/v1")
    custom = [
        {
            "category_name": "Custom Risk",
            "topics": ["society,legal,fraud,,"],
        }
    ]

    called_categories: list[str] = []

    async def _fake_category(**kwargs: Any) -> list:
        called_categories.append(kwargs["category"]["category_name"])
        return []

    with (
        patch.object(
            service,
            "get_company_data",
            AsyncMock(
                return_value=MagicMock(
                    entity_id="E09E2B",
                    company_name="Apple Inc.",
                )
            ),
        ),
        patch.object(service, "search_negative_category", side_effect=_fake_category),
    ):
        # CompanyData is a pydantic/dataclass-like - check what get_company_data returns
        from services.company_cache import CompanyData

        service.get_company_data = AsyncMock(
            return_value=CompanyData(
                ticker="AAPL",
                entity_id="E09E2B",
                company_name="Apple Inc.",
            )
        )
        result = await service.search_negative_news(
            "AAPL",
            days=7,
            custom_categories=custom,
            min_relevance=0.0,
        )

    assert called_categories == ["Custom Risk"]
    assert result["ticker"] == "AAPL"
    assert result["topic_results"] == []
    await service.close()

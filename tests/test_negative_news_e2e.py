"""Live end-to-end negative news search against Bigdata.com API."""

from __future__ import annotations

import asyncio
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

BIGDATA_API_KEY = os.getenv("BIGDATA_API_KEY", "").strip()
HAS_LIVE_KEY = bool(BIGDATA_API_KEY) and BIGDATA_API_KEY not in {
    "YOUR_KEY_HERE",
    "your_api_key_here",
}


@pytest.mark.e2e
@pytest.mark.skipif(not HAS_LIVE_KEY, reason="BIGDATA_API_KEY not configured")
def test_negative_news_live_api_aapl() -> None:
    """POST-equivalent live search: negative news for AAPL over 90 days."""
    from services.topic_search_service import TopicSearchService

    async def _run() -> dict:
        service = TopicSearchService(
            api_key=BIGDATA_API_KEY,
            base_url="https://api.bigdata.com/v1",
        )
        try:
            # Use a subset of categories to keep the live call cheaper / faster
            categories = [
                {
                    "category_name": "Litigation / Misconduct",
                    "topics": [
                        "society,legal,legal-issues,,",
                        "society,legal,fraud,,",
                        "society,legal,antitrust-investigation,,",
                    ],
                },
                {
                    "category_name": "Regulatory",
                    "topics": [
                        "business,regulatory,regulatory-investigation,,",
                        "business,earnings,earnings,probe,",
                    ],
                },
                {
                    "category_name": "Operational / cyber",
                    "topics": [
                        "society,cyber-security,data-breach,,",
                        "business,products-services,product-recall,,",
                    ],
                },
            ]
            return await service.search_negative_news(
                "AAPL",
                days=90,
                custom_categories=categories,
                min_relevance=0.0,
            )
        finally:
            await service.close()

    result = asyncio.run(_run())

    assert "error" not in result, result.get("error")
    assert result["ticker"] == "AAPL"
    assert result.get("entity_id")
    assert result.get("company_name")
    assert isinstance(result["topic_results"], list)
    assert result["total_results"] == len(result["topic_results"])

    for article in result["topic_results"]:
        assert article.get("search_type") == "negative"
        assert article.get("topic_name")
        assert article.get("headline")
        assert "relevance" in article

    # Soft signal: liquid names usually have some negative public news in 90d
    if result["total_results"] == 0:
        pytest.skip("No negative news hits for AAPL in 90d window (shape OK)")


@pytest.mark.e2e
@pytest.mark.skipif(not HAS_LIVE_KEY, reason="BIGDATA_API_KEY not configured")
def test_negative_news_live_http_endpoint() -> None:
    """End-to-end via FastAPI TestClient POST /api/news/{ticker}."""
    import httpx
    from fastapi.testclient import TestClient

    # Import after env is loaded so main.py accepts the key
    import main as app_module

    with TestClient(app_module.app) as client:
        response = client.post(
            "/api/news/AAPL",
            json={
                "negative_news": True,
                "basic_search": False,
                "days": 90,
                "relevance": 0.0,
                "negative_categories": [
                    {
                        "category_name": "Regulatory",
                        "topics": [
                            "business,regulatory,regulatory-investigation,,",
                            "business,earnings,earnings,probe,",
                        ],
                    }
                ],
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data.get("entity_id")
    assert "topic_results" in data
    assert data["settings"]["negative_news"] is True
    for article in data["topic_results"]:
        assert article["search_type"] == "negative"

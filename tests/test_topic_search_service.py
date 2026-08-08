"""Tests for TopicSearchService query building, article formatting and sector search.

These guard the shared helpers (``_build_filters``, ``_post_search``, ``_format_article``)
that both the entity-scoped and theme-scoped search paths are built on.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from services.topic_search_service import TOTAL_CHUNK_BUDGET, TopicSearchService

BASELINE_ARTICLE_KEYS = {
    "id",
    "headline",
    "timestamp",
    "time_ago",
    "source",
    "summary",
    "full_text",
    "document_url",
    "relevance",
    "document_type",
    "detections",
    "search_type",
    "topic",
    "ticker",
}

TOPIC_ARTICLE_KEYS = BASELINE_ARTICLE_KEYS | {"topic_name", "topic_index"}

THEME_ARTICLE_KEYS = (BASELINE_ARTICLE_KEYS - {"ticker"}) | {
    "topic_name",
    "topic_index",
    "sector",
}


@pytest.fixture
def service() -> TopicSearchService:
    return TopicSearchService(api_key="test-key")


def make_result_item(doc_id: str, relevance: float = 0.5, text: str = "chunk text") -> dict[str, Any]:
    """Build a deduplicated ``_post_search`` item as the real method would return it."""
    return {
        "article": {
            "id": doc_id,
            "headline": f"Headline {doc_id}",
            "timestamp": "2026-07-30T12:00:00Z",
            "source": {"name": "Example Source"},
            "url": f"https://example.com/{doc_id}",
            "document_type": "NEWS",
        },
        "best_chunk": {"text": text, "detections": [{"id": "E1", "start": 0, "end": 5}]},
        "relevance": relevance,
    }


def stub_post_search(service: TopicSearchService, responses: dict[str, list[dict[str, Any]]]):
    """Replace ``_post_search`` with a stub keyed by query text; records every call."""
    calls: list[dict[str, Any]] = []

    async def fake_post_search(text, filters, max_chunks, log_label, error_log_level=None):
        calls.append(
            {
                "text": text,
                "filters": filters,
                "max_chunks": max_chunks,
                "log_label": log_label,
            }
        )
        return responses.get(text, [])

    service._post_search = fake_post_search  # type: ignore[method-assign]
    return calls


# ── _build_filters ───────────────────────────────────────────────────────────

def test_build_filters_includes_entity_when_given(service: TopicSearchService) -> None:
    filters = service._build_filters(7, entity_id="ABC123")
    assert filters["entity"] == {"all_of": ["ABC123"]}


def test_build_filters_omits_entity_for_theme_search(service: TopicSearchService) -> None:
    """Sector search relies on there being no entity filter at all."""
    filters = service._build_filters(7)
    assert "entity" not in filters


def test_build_filters_sentiment_is_opt_in(service: TopicSearchService) -> None:
    assert "sentiment" not in service._build_filters(7)
    assert service._build_filters(7, sentiment=True)["sentiment"] == {
        "values": ["positive", "negative"]
    }


def test_build_filters_defaults_source_categories(service: TopicSearchService) -> None:
    filters = service._build_filters(7)
    assert filters["category"] == {
        "mode": "INCLUDE",
        "values": ["news_public", "transcripts"],
    }


def test_build_filters_timestamp_window_is_ordered(service: TopicSearchService) -> None:
    filters = service._build_filters(7)
    timestamp = filters["timestamp"]
    assert timestamp["start"] < timestamp["end"]
    assert timestamp["end"].endswith("Z")


def test_build_filters_accepts_fractional_days(service: TopicSearchService) -> None:
    """Incremental refresh passes minutes converted to fractional days."""
    filters = service._build_filters(1 / (60 * 24))
    assert filters["timestamp"]["start"] < filters["timestamp"]["end"]


# ── _format_article ──────────────────────────────────────────────────────────

def test_format_article_shape(service: TopicSearchService) -> None:
    item = make_result_item("DOC1", relevance=0.42)

    article = service._format_article(
        item["article"],
        item["best_chunk"],
        item["relevance"],
        fallback_id="fallback_0",
        search_type="baseline",
        topic=None,
        ticker="AAPL",
    )

    assert set(article) == BASELINE_ARTICLE_KEYS
    assert article["id"] == "DOC1"
    assert article["headline"] == "Headline DOC1"
    assert article["source"] == "Example Source"
    assert article["document_url"] == "https://example.com/DOC1"
    assert article["relevance"] == 0.42
    assert article["full_text"] == "chunk text"
    assert article["detections"] == [{"id": "E1", "start": 0, "end": 5}]


def test_format_article_uses_fallback_id_when_missing(service: TopicSearchService) -> None:
    article = service._format_article({}, {}, 0.0, fallback_id="theme_3_1")
    assert article["id"] == "theme_3_1"
    assert article["headline"] == "No headline"
    assert article["source"] == "Unknown"
    assert article["document_type"] == "NEWS"


def test_format_article_truncates_summary_but_keeps_full_text(service: TopicSearchService) -> None:
    long_text = "x" * 500
    item = make_result_item("DOC1", text=long_text)

    article = service._format_article(item["article"], item["best_chunk"], 0.5, fallback_id="f")

    assert article["summary"] == "x" * 200 + "..."
    assert article["full_text"] == long_text


def test_format_article_short_summary_is_not_suffixed(service: TopicSearchService) -> None:
    item = make_result_item("DOC1", text="short chunk")
    article = service._format_article(item["article"], item["best_chunk"], 0.5, fallback_id="f")
    assert article["summary"] == "short chunk"


# ── search_baseline / search_single_topic ────────────────────────────────────

def test_search_baseline_keeps_legacy_article_shape(service: TopicSearchService) -> None:
    calls = stub_post_search(service, {"earnings financial results stock news": [make_result_item("D1")]})

    articles = asyncio.run(service.search_baseline("AAPL", "ENT1", days=7))

    assert len(articles) == 1
    assert set(articles[0]) == BASELINE_ARTICLE_KEYS
    assert articles[0]["search_type"] == "baseline"
    assert articles[0]["topic"] is None
    assert articles[0]["ticker"] == "AAPL"
    # Baseline stays entity-scoped and unfiltered by sentiment
    assert calls[0]["filters"]["entity"] == {"all_of": ["ENT1"]}
    assert "sentiment" not in calls[0]["filters"]


def test_search_single_topic_formats_company_and_filters_sentiment(
    service: TopicSearchService,
) -> None:
    calls = stub_post_search(service, {"Apple Inc earnings beat": [make_result_item("D1")]})

    articles = asyncio.run(
        service.search_single_topic(
            "AAPL",
            "ENT1",
            "Apple Inc",
            {"topic_name": "Financial Metrics", "topic_text": "{company} earnings beat"},
            0,
            days=7,
        )
    )

    assert calls[0]["text"] == "Apple Inc earnings beat"
    assert calls[0]["filters"]["entity"] == {"all_of": ["ENT1"]}
    assert calls[0]["filters"]["sentiment"] == {"values": ["positive", "negative"]}
    assert set(articles[0]) == TOPIC_ARTICLE_KEYS
    assert articles[0]["search_type"] == "topic"
    assert articles[0]["topic_name"] == "Financial Metrics"
    assert articles[0]["topic_index"] == 0


# ── search_single_theme ──────────────────────────────────────────────────────

def test_search_single_theme_sends_phrase_verbatim_without_entity(
    service: TopicSearchService,
) -> None:
    phrase = "Brent and WTI crude oil prices rise on supply outlook"
    calls = stub_post_search(service, {phrase: [make_result_item("D1", relevance=0.7)]})

    articles = asyncio.run(
        service.search_single_theme(
            {"topic_name": "Crude Prices", "topic_text": phrase},
            0,
            days=7,
            sector="energy",
        )
    )

    assert calls[0]["text"] == phrase
    assert "entity" not in calls[0]["filters"]
    assert set(articles[0]) == THEME_ARTICLE_KEYS
    assert articles[0]["search_type"] == "theme"
    assert articles[0]["topic"] == phrase
    assert articles[0]["topic_name"] == "Crude Prices"
    assert articles[0]["sector"] == "energy"


def test_search_single_theme_accepts_plain_string(service: TopicSearchService) -> None:
    calls = stub_post_search(service, {"oil sanctions": [make_result_item("D1")]})

    articles = asyncio.run(service.search_single_theme("oil sanctions", 2, sector="energy"))

    assert calls[0]["text"] == "oil sanctions"
    assert articles[0]["topic_name"] == "Topic 3"


def test_search_single_theme_skips_blank_phrase(service: TopicSearchService) -> None:
    calls = stub_post_search(service, {})

    articles = asyncio.run(
        service.search_single_theme({"topic_name": "Empty", "topic_text": "   "}, 0)
    )

    assert articles == []
    assert calls == []


# ── search_sector ────────────────────────────────────────────────────────────

def test_search_sector_dedupes_across_themes_and_filters_relevance(
    service: TopicSearchService,
) -> None:
    topics = [
        {"topic_name": "Crude Prices", "topic_text": "phrase a"},
        {"topic_name": "Sanctions", "topic_text": "phrase b"},
    ]
    stub_post_search(
        service,
        {
            "phrase a": [make_result_item("D1", 0.9), make_result_item("D2", 0.2)],
            "phrase b": [make_result_item("D1", 0.4), make_result_item("D3", 0.8)],
        },
    )

    results = asyncio.run(
        service.search_sector("energy", topics, days=7, min_relevance=0.3, sector_label="Energy")
    )

    by_id = {a["id"]: a for a in results["theme_results"]}
    # D1 appears under both phrases and keeps its highest relevance; D2 is below threshold
    assert set(by_id) == {"D1", "D3"}
    assert by_id["D1"]["relevance"] == 0.9
    assert results["total_results"] == 2
    assert results["sector"] == "energy"
    assert results["sector_label"] == "Energy"
    assert results["search_stats"]["topics_searched"] == 2


def test_search_sector_divides_chunk_budget_across_topics(service: TopicSearchService) -> None:
    topics = [{"topic_name": f"T{i}", "topic_text": f"phrase {i}"} for i in range(4)]
    calls = stub_post_search(service, {})

    asyncio.run(service.search_sector("energy", topics))

    assert len(calls) == 4
    assert all(call["max_chunks"] == TOTAL_CHUNK_BUDGET // 4 for call in calls)


def test_search_sector_with_no_topics_makes_no_requests(service: TopicSearchService) -> None:
    calls = stub_post_search(service, {})

    results = asyncio.run(service.search_sector("energy", [], sector_label="Energy"))

    assert results["total_results"] == 0
    assert results["theme_results"] == []
    assert results["search_stats"]["topics_searched"] == 0
    assert calls == []


def test_search_sector_tags_every_article_with_sector(service: TopicSearchService) -> None:
    topics = [{"topic_name": "Crude Prices", "topic_text": "phrase a"}]
    stub_post_search(service, {"phrase a": [make_result_item("D1"), make_result_item("D2")]})

    results = asyncio.run(service.search_sector("energy", topics))

    assert [a["sector"] for a in results["theme_results"]] == ["energy", "energy"]


def test_search_sector_accepts_fractional_days_for_incremental_refresh(
    service: TopicSearchService,
) -> None:
    """Auto-refresh sends since_minutes, which the API converts to fractional days."""
    topics = [{"topic_name": "Crude Prices", "topic_text": "phrase a"}]
    calls = stub_post_search(service, {"phrase a": [make_result_item("D1")]})

    results = asyncio.run(service.search_sector("energy", topics, days=5 / (60 * 24)))

    assert results["total_results"] == 1
    window = calls[0]["filters"]["timestamp"]
    assert window["start"] < window["end"]


# ── search_sector with AI query expansion ────────────────────────────────────

def stub_theme_variations(service: TopicSearchService, variations_by_phrase):
    """Replace Gemini variation generation with a stub; records the prompts used."""
    prompts: list[str] = []

    async def fake_generate(topic, expansion_prompt):
        prompts.append(expansion_prompt)
        text = topic["topic_text"] if isinstance(topic, dict) else topic
        return list(variations_by_phrase.get(text, []))

    service.generate_theme_variations = fake_generate  # type: ignore[method-assign]
    return prompts


def test_search_sector_without_expansion_does_not_call_gemini(
    service: TopicSearchService,
) -> None:
    topics = [{"topic_name": "Crude Prices", "topic_text": "phrase a"}]
    prompts = stub_theme_variations(service, {})
    calls = stub_post_search(service, {"phrase a": [make_result_item("D1")]})

    results = asyncio.run(service.search_sector("energy", topics))

    assert prompts == []
    assert len(calls) == 1
    assert results["search_stats"]["query_reformulation"] is False
    assert results["search_stats"]["variations_generated"] == 0
    assert results["search_stats"]["queries_executed"] == 1


def test_search_sector_expansion_searches_originals_and_variations(
    service: TopicSearchService,
) -> None:
    topics = [{"topic_name": "Crude Prices", "topic_text": "phrase a"}]
    stub_theme_variations(service, {"phrase a": ["variation 1", "variation 2", "variation 3"]})
    calls = stub_post_search(
        service,
        {
            "phrase a": [make_result_item("D1", 0.5)],
            "variation 1": [make_result_item("D2", 0.6)],
            "variation 2": [make_result_item("D3", 0.7)],
            "variation 3": [make_result_item("D1", 0.9)],  # rediscovers D1 at higher relevance
        },
    )

    results = asyncio.run(
        service.search_sector("energy", topics, query_reformulation=True, expansion_prompt="P")
    )

    assert [call["text"] for call in calls] == [
        "phrase a",
        "variation 1",
        "variation 2",
        "variation 3",
    ]
    assert results["search_stats"]["topics_searched"] == 1
    assert results["search_stats"]["queries_executed"] == 4
    assert results["search_stats"]["variations_generated"] == 3
    assert results["search_stats"]["query_reformulation"] is True

    by_id = {a["id"]: a for a in results["theme_results"]}
    assert set(by_id) == {"D1", "D2", "D3"}
    assert by_id["D1"]["relevance"] == 0.9


def test_search_sector_expansion_keeps_parent_topic_name_for_tabs(
    service: TopicSearchService,
) -> None:
    """Variations must collapse into the parent's topic tab, not create new ones."""
    topics = [{"topic_name": "Crude Prices", "topic_text": "phrase a"}]
    stub_theme_variations(service, {"phrase a": ["variation 1"]})
    stub_post_search(
        service,
        {
            "phrase a": [make_result_item("D1")],
            "variation 1": [make_result_item("D2")],
        },
    )

    results = asyncio.run(
        service.search_sector("energy", topics, query_reformulation=True, expansion_prompt="P")
    )

    assert {a["topic_name"] for a in results["theme_results"]} == {"Crude Prices"}
    # The variation's own text is still recorded as the query that found the article
    assert {a["topic"] for a in results["theme_results"]} == {"phrase a", "variation 1"}


def test_search_sector_expansion_passes_sector_prompt_to_gemini(
    service: TopicSearchService,
) -> None:
    topics = [
        {"topic_name": "Crude Prices", "topic_text": "phrase a"},
        {"topic_name": "Sanctions", "topic_text": "phrase b"},
    ]
    prompts = stub_theme_variations(service, {})
    stub_post_search(service, {})

    asyncio.run(
        service.search_sector(
            "energy", topics, query_reformulation=True, expansion_prompt="ENERGY DESK PROMPT"
        )
    )

    assert prompts == ["ENERGY DESK PROMPT", "ENERGY DESK PROMPT"]


def test_search_sector_expansion_divides_chunk_budget_across_all_queries(
    service: TopicSearchService,
) -> None:
    topics = [{"topic_name": "Crude Prices", "topic_text": "phrase a"}]
    stub_theme_variations(service, {"phrase a": ["v1", "v2", "v3"]})
    calls = stub_post_search(service, {})

    asyncio.run(
        service.search_sector("energy", topics, query_reformulation=True, expansion_prompt="P")
    )

    assert all(call["max_chunks"] == TOTAL_CHUNK_BUDGET // 4 for call in calls)


def test_search_sector_survives_failed_variation_generation(
    service: TopicSearchService,
) -> None:
    """A Gemini failure must degrade to the original phrase, not fail the search."""
    topics = [{"topic_name": "Crude Prices", "topic_text": "phrase a"}]

    async def failing_generate(topic, expansion_prompt):
        raise RuntimeError("gemini unavailable")

    service.generate_theme_variations = failing_generate  # type: ignore[method-assign]
    calls = stub_post_search(service, {"phrase a": [make_result_item("D1")]})

    results = asyncio.run(
        service.search_sector("energy", topics, query_reformulation=True, expansion_prompt="P")
    )

    assert [call["text"] for call in calls] == ["phrase a"]
    assert results["total_results"] == 1
    assert results["search_stats"]["variations_generated"] == 0

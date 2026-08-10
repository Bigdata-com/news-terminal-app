"""Tests for negative news configuration helpers."""

from __future__ import annotations

import config.topics as topics_module

from config.topics import (
    NEGATIVE_NEWS_CATEGORIES,
    NEGATIVE_NEWS_CATEGORIES_REVISION,
    NEGATIVE_NEWS_ENTITY_BATCH_SIZE,
    NEGATIVE_NEWS_ENTITY_SEARCH_IN,
    NEGATIVE_NEWS_SENTIMENT_RANGES,
    safe_negative_news_categories_revision,
)
from services.topic_search_service import TopicSearchService


def test_negative_news_revision_is_positive_integer() -> None:
    assert isinstance(NEGATIVE_NEWS_CATEGORIES_REVISION, int)
    assert NEGATIVE_NEWS_CATEGORIES_REVISION >= 1
    assert safe_negative_news_categories_revision() >= 1


def test_safe_negative_revision_invalid_falls_back(
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(topics_module, "NEGATIVE_NEWS_CATEGORIES_REVISION", "bad")
    assert safe_negative_news_categories_revision() == 1


def test_negative_news_categories_structure() -> None:
    assert len(NEGATIVE_NEWS_CATEGORIES) == 5
    names = [c["category_name"] for c in NEGATIVE_NEWS_CATEGORIES]
    assert names == [
        "Litigation / Misconduct",
        "Regulatory",
        "Credit stress",
        "Governance / leadership",
        "Operational / cyber",
    ]
    for category in NEGATIVE_NEWS_CATEGORIES:
        topics = category["topics"]
        assert isinstance(topics, list)
        assert len(topics) >= 1
        for topic in topics:
            assert isinstance(topic, str)
            assert topic.count(",") >= 3


def test_negative_news_expected_group_sizes() -> None:
    sizes = {c["category_name"]: len(c["topics"]) for c in NEGATIVE_NEWS_CATEGORIES}
    assert sizes["Litigation / Misconduct"] == 7
    assert sizes["Regulatory"] == 6
    assert sizes["Credit stress"] == 7
    assert sizes["Governance / leadership"] == 3
    assert sizes["Operational / cyber"] == 3


def test_entity_batch_size_is_one() -> None:
    """One entity per request keeps ticker attribution unambiguous."""
    assert NEGATIVE_NEWS_ENTITY_BATCH_SIZE == 1


def test_entity_search_in_is_headline() -> None:
    """Headline matching drops articles that only mention the company in passing."""
    assert NEGATIVE_NEWS_ENTITY_SEARCH_IN == "HEADLINE"


def test_sentiment_ranges_are_strongly_negative() -> None:
    assert NEGATIVE_NEWS_SENTIMENT_RANGES == [{"min": -1, "max": -0.1}]


def test_chunk_list_batches_one_entity_each() -> None:
    items = list(range(3))
    batches = TopicSearchService._chunk_list(items, NEGATIVE_NEWS_ENTITY_BATCH_SIZE)
    assert batches == [[0], [1], [2]]


def test_chunk_list_supports_larger_batches() -> None:
    items = list(range(7))
    assert TopicSearchService._chunk_list(items, 5) == [[0, 1, 2, 3, 4], [5, 6]]

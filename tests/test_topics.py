"""Tests for default topic configuration helpers."""

from __future__ import annotations

import config.topics as topics_module
import pytest

from config.topics import (
    DEFAULT_TOPICS,
    DEFAULT_TOPICS_REVISION,
    TOPIC_CATEGORIES,
    get_topic_category,
    normalize_topic_category_slug,
    safe_default_topics_revision,
)


def test_default_topics_revision_is_positive_integer() -> None:
    """Web UI only syncs when revision is a finite integer >= 1 (see static/app.js)."""
    assert isinstance(DEFAULT_TOPICS_REVISION, int)
    assert DEFAULT_TOPICS_REVISION >= 1


def test_safe_default_topics_revision_coerces_numeric_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(topics_module, "DEFAULT_TOPICS_REVISION", "7")
    assert safe_default_topics_revision() == 7


def test_safe_default_topics_revision_invalid_falls_back_to_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(topics_module, "DEFAULT_TOPICS_REVISION", "not-a-number")
    assert safe_default_topics_revision() == 1


def test_safe_default_topics_revision_zero_falls_back_to_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(topics_module, "DEFAULT_TOPICS_REVISION", 0)
    assert safe_default_topics_revision() == 1


def test_default_topics_and_categories_in_sync() -> None:
    indices = sorted(i for ids in TOPIC_CATEGORIES.values() for i in ids)
    assert indices == list(range(len(DEFAULT_TOPICS)))


def test_get_topic_category_known_indices() -> None:
    assert get_topic_category(0) == "financial_metrics"
    assert get_topic_category(11) == "products"
    assert get_topic_category(28) == "markets"


def test_get_topic_category_uncategorized() -> None:
    assert get_topic_category(999) == "uncategorized"


def test_normalize_topic_category_slug_legacy() -> None:
    assert normalize_topic_category_slug("earnings") == "financial_metrics"
    assert normalize_topic_category_slug("CAPITAL") == "financing"
    assert normalize_topic_category_slug("financial_metrics") == "financial_metrics"

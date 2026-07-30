"""Tests for sector (theme) topic configuration helpers."""

from __future__ import annotations

import config.sector_topics as sector_topics_module
import pytest

from config.sector_topics import (
    ENERGY_EXPANSION_PROMPT,
    ENERGY_TOPICS,
    SECTOR_TOPICS_REVISION,
    SECTORS,
    UnknownSectorError,
    default_topics_by_sector,
    get_sector,
    get_sector_expansion_prompt,
    list_sectors,
    safe_sector_topics_revision,
)


def test_sector_topics_revision_is_positive_integer() -> None:
    """Web UI only syncs when revision is a finite integer >= 1 (see static/sector.js)."""
    assert isinstance(SECTOR_TOPICS_REVISION, int)
    assert SECTOR_TOPICS_REVISION >= 1


def test_safe_sector_topics_revision_coerces_numeric_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sector_topics_module, "SECTOR_TOPICS_REVISION", "5")
    assert safe_sector_topics_revision() == 5


def test_safe_sector_topics_revision_invalid_falls_back_to_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sector_topics_module, "SECTOR_TOPICS_REVISION", "not-a-number")
    assert safe_sector_topics_revision() == 1


def test_safe_sector_topics_revision_zero_falls_back_to_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sector_topics_module, "SECTOR_TOPICS_REVISION", 0)
    assert safe_sector_topics_revision() == 1


def test_energy_topics_have_no_company_placeholder() -> None:
    """Sector phrases are sent verbatim, so a {company} placeholder would be searched literally."""
    for topic in ENERGY_TOPICS:
        assert "{company}" not in topic["topic_text"]
        assert "{" not in topic["topic_text"]


def test_energy_topics_have_non_empty_name_and_text() -> None:
    for topic in ENERGY_TOPICS:
        assert set(topic) == {"topic_name", "topic_text"}
        assert topic["topic_name"].strip()
        assert topic["topic_text"].strip()


def test_energy_topic_names_are_usable_as_tab_labels() -> None:
    """The UI renders topic_name uppercased in a narrow tab, so keep labels short."""
    for topic in ENERGY_TOPICS:
        assert len(topic["topic_name"]) <= 24


def test_get_sector_is_case_and_whitespace_insensitive() -> None:
    assert get_sector("energy")["id"] == "energy"
    assert get_sector("  ENERGY  ")["id"] == "energy"


def test_get_sector_returns_topics() -> None:
    assert get_sector("energy")["topics"] == ENERGY_TOPICS


def test_get_sector_raises_for_disabled_sector() -> None:
    disabled = next(s for s in SECTORS if not s["enabled"])
    with pytest.raises(UnknownSectorError, match="not available yet"):
        get_sector(disabled["id"])


def test_get_sector_raises_for_unknown_sector() -> None:
    with pytest.raises(UnknownSectorError, match="Unknown sector"):
        get_sector("does-not-exist")


def test_list_sectors_exposes_tile_metadata_without_payloads() -> None:
    listed = list_sectors()

    assert len(listed) == len(SECTORS)
    for entry in listed:
        assert set(entry) == {"id", "label", "description", "enabled", "topic_count"}

    by_id = {entry["id"]: entry for entry in listed}
    assert by_id["energy"]["enabled"] is True
    assert by_id["energy"]["topic_count"] == len(ENERGY_TOPICS)


def test_disabled_sectors_have_no_topics() -> None:
    for sector in SECTORS:
        if not sector["enabled"]:
            assert sector["topics"] == []
            assert sector["description"].strip()


def test_sector_ids_are_unique() -> None:
    ids = [sector["id"] for sector in SECTORS]
    assert len(ids) == len(set(ids))


def test_energy_expansion_prompt_is_desk_specific() -> None:
    """A generic prompt yields synonym swaps; the desk vocabulary is what makes expansion useful."""
    prompt = get_sector_expansion_prompt("energy")

    assert prompt == ENERGY_EXPANSION_PROMPT
    for term in ("Brent", "WTI", "OPEC+", "crack spread", "Hormuz", "LNG"):
        assert term.lower() in prompt.lower()


def test_energy_expansion_prompt_has_no_company_placeholder() -> None:
    assert "{company}" not in ENERGY_EXPANSION_PROMPT
    assert "{" not in ENERGY_EXPANSION_PROMPT


def test_get_sector_expansion_prompt_falls_back_for_sector_without_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sector can be enabled before its bespoke prompt is written."""
    sectors_without_prompt = [
        {
            "id": "test_sector",
            "label": "Test Desk",
            "description": "d",
            "enabled": True,
            "topics": [{"topic_name": "T", "topic_text": "phrase"}],
            "expansion_prompt": "   ",
        }
    ]
    monkeypatch.setattr(sector_topics_module, "SECTORS", sectors_without_prompt)

    prompt = sector_topics_module.get_sector_expansion_prompt("test_sector")

    assert "Test Desk" in prompt
    assert prompt.strip()


def test_get_sector_expansion_prompt_raises_for_disabled_sector() -> None:
    disabled = next(s for s in SECTORS if not s["enabled"])
    with pytest.raises(UnknownSectorError):
        get_sector_expansion_prompt(disabled["id"])


def test_every_enabled_sector_has_an_expansion_prompt() -> None:
    for sector in SECTORS:
        if sector["enabled"]:
            assert sector["expansion_prompt"].strip()


def test_list_sectors_does_not_leak_expansion_prompts() -> None:
    """Prompts are server-side configuration, not payload for the browser."""
    for entry in list_sectors():
        assert "expansion_prompt" not in entry


def test_default_topics_by_sector_covers_enabled_sectors_only() -> None:
    defaults = default_topics_by_sector()
    enabled_ids = {s["id"] for s in SECTORS if s["enabled"]}

    assert set(defaults) == enabled_ids
    assert defaults["energy"] == ENERGY_TOPICS

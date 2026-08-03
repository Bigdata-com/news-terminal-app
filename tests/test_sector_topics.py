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

# Every desk must be covered by the structural checks below, so drive them off the registry.
ALL_TOPICS: list[tuple[str, dict[str, str]]] = [
    (sector["id"], topic) for sector in SECTORS for topic in sector["topics"]
]
SECTOR_IDS: list[str] = [sector["id"] for sector in SECTORS]
ENABLED_SECTOR_IDS: list[str] = [sector["id"] for sector in SECTORS if sector["enabled"]]
HIDDEN_SECTOR_IDS: list[str] = [sector["id"] for sector in SECTORS if not sector["enabled"]]

DISABLED_SECTOR: list[dict[str, object]] = [
    {
        "id": "not_ready",
        "label": "Not Ready",
        "description": "Placeholder desk",
        "enabled": False,
        "topics": [],
        "expansion_prompt": "",
    }
]


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


@pytest.mark.parametrize(("sector_id", "topic"), ALL_TOPICS)
def test_topics_have_no_company_placeholder(sector_id: str, topic: dict[str, str]) -> None:
    """Sector phrases are sent verbatim, so a {company} placeholder would be searched literally."""
    assert "{company}" not in topic["topic_text"]
    assert "{" not in topic["topic_text"]


@pytest.mark.parametrize(("sector_id", "topic"), ALL_TOPICS)
def test_topics_have_non_empty_name_and_text(sector_id: str, topic: dict[str, str]) -> None:
    assert set(topic) == {"topic_name", "topic_text"}
    assert topic["topic_name"].strip()
    assert topic["topic_text"].strip()


@pytest.mark.parametrize(("sector_id", "topic"), ALL_TOPICS)
def test_topic_names_are_usable_as_tab_labels(sector_id: str, topic: dict[str, str]) -> None:
    """The UI renders topic_name uppercased in a narrow tab, so keep labels short."""
    assert len(topic["topic_name"]) <= 24


@pytest.mark.parametrize("sector_id", SECTOR_IDS)
def test_topic_texts_are_unique_within_a_sector(sector_id: str) -> None:
    """Duplicate phrases waste a search slot and add nothing after deduplication."""
    sector = next(entry for entry in SECTORS if entry["id"] == sector_id)
    texts = [topic["topic_text"] for topic in sector["topics"]]
    assert len(texts) == len(set(texts))


@pytest.mark.parametrize("sector_id", ENABLED_SECTOR_IDS)
def test_enabled_sectors_have_topics_and_a_prompt(sector_id: str) -> None:
    sector = get_sector(sector_id)

    assert sector["topics"], f"{sector_id} is enabled but has no topics"
    assert sector["expansion_prompt"].strip()
    assert sector["description"].strip()


def test_get_sector_is_case_and_whitespace_insensitive() -> None:
    assert get_sector("energy")["id"] == "energy"
    assert get_sector("  ENERGY  ")["id"] == "energy"


def test_get_sector_returns_topics() -> None:
    assert get_sector("energy")["topics"] == ENERGY_TOPICS


def test_get_sector_raises_for_disabled_sector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sector_topics_module, "SECTORS", DISABLED_SECTOR)
    with pytest.raises(UnknownSectorError, match="not available yet"):
        sector_topics_module.get_sector("not_ready")


def test_get_sector_raises_for_unknown_sector() -> None:
    with pytest.raises(UnknownSectorError, match="Unknown sector"):
        get_sector("does-not-exist")


def test_list_sectors_exposes_tile_metadata_without_payloads() -> None:
    listed = list_sectors()

    assert len(listed) == len(ENABLED_SECTOR_IDS)
    assert [entry["id"] for entry in listed] == ENABLED_SECTOR_IDS
    for entry in listed:
        assert set(entry) == {"id", "label", "description", "enabled", "topic_count"}
        assert entry["enabled"] is True

    by_id = {entry["id"]: entry for entry in listed}
    assert by_id["energy"]["topic_count"] == len(ENERGY_TOPICS)
    assert by_id["utilities_power"]["label"] == "Power"
    assert by_id["metals_mining"]["label"] == "Metals"


def test_disabled_sectors_are_hidden_from_list_sectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled desks stay in the registry but are omitted from the tile API."""
    monkeypatch.setattr(sector_topics_module, "SECTORS", DISABLED_SECTOR)

    listed = sector_topics_module.list_sectors()

    assert listed == []
    assert sector_topics_module.default_topics_by_sector() == {}


def test_hidden_desks_remain_registered_but_disabled() -> None:
    assert set(HIDDEN_SECTOR_IDS) == {"finance", "technology", "insurance"}
    for sector_id in HIDDEN_SECTOR_IDS:
        with pytest.raises(UnknownSectorError, match="not available yet"):
            get_sector(sector_id)


def test_sector_ids_are_unique() -> None:
    ids = [sector["id"] for sector in SECTORS]
    assert len(ids) == len(set(ids))


def test_sector_ids_are_url_and_storage_safe() -> None:
    """Ids travel in the /api/sector-news body and key the browser's cached topic lists."""
    for sector_id in SECTOR_IDS:
        assert sector_id == sector_id.lower()
        assert sector_id.replace("_", "").isalnum()


def test_expected_sector_desks_are_registered() -> None:
    expected = {
        "energy",
        "metals_mining",
        "utilities_power",
        "shipping_freight",
        "finance",
        "technology",
        "insurance",
    }
    assert expected.issubset(set(SECTOR_IDS))
    assert ENABLED_SECTOR_IDS == [
        "energy",
        "utilities_power",
        "shipping_freight",
        "metals_mining",
    ]


def test_energy_expansion_prompt_is_desk_specific() -> None:
    """A generic prompt yields synonym swaps; the desk vocabulary is what makes expansion useful."""
    prompt = get_sector_expansion_prompt("energy")

    assert prompt == ENERGY_EXPANSION_PROMPT
    for term in ("Brent", "WTI", "OPEC+", "crack spread", "Hormuz", "LNG"):
        assert term.lower() in prompt.lower()


@pytest.mark.parametrize(
    ("sector_id", "terms"),
    [
        ("metals_mining", ("LME", "iron ore", "AISC", "smelter")),
        ("utilities_power", ("PJM", "ERCOT", "capacity auction", "rate case")),
        ("shipping_freight", ("Baltic Dry Index", "Worldscale", "Panama Canal", "VLSFO")),
    ],
)
def test_sector_expansion_prompts_carry_desk_vocabulary(
    sector_id: str, terms: tuple[str, ...]
) -> None:
    prompt = get_sector_expansion_prompt(sector_id)
    for term in terms:
        assert term.lower() in prompt.lower()


@pytest.mark.parametrize("sector_id", ENABLED_SECTOR_IDS)
def test_expansion_prompts_have_no_company_placeholder(sector_id: str) -> None:
    prompt = get_sector_expansion_prompt(sector_id)
    assert "{company}" not in prompt
    assert "{" not in prompt


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


def test_get_sector_expansion_prompt_raises_for_disabled_sector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sector_topics_module, "SECTORS", DISABLED_SECTOR)
    with pytest.raises(UnknownSectorError):
        sector_topics_module.get_sector_expansion_prompt("not_ready")


def test_list_sectors_does_not_leak_expansion_prompts() -> None:
    """Prompts are server-side configuration, not payload for the browser."""
    for entry in list_sectors():
        assert "expansion_prompt" not in entry


def test_default_topics_by_sector_covers_enabled_sectors_only() -> None:
    defaults = default_topics_by_sector()
    enabled_ids = {s["id"] for s in SECTORS if s["enabled"]}

    assert set(defaults) == enabled_ids
    assert defaults["energy"] == ENERGY_TOPICS

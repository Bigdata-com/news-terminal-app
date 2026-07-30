"""
Sector (theme) topic templates for non-entity news searches.

Unlike ``config.topics``, these phrases contain **no** ``{company}`` placeholder:
sector searches run against the Bigdata.com Search API without an entity filter,
so the phrase text is sent verbatim as the semantic query.

Each topic is a ``{"topic_name", "topic_text"}`` pair. ``topic_name`` doubles as
the filter-tab label in the web UI, so several phrases may share one name.
"""

from __future__ import annotations

from typing import Any, TypeAlias

SectorTopic: TypeAlias = dict[str, str]
Sector: TypeAlias = dict[str, Any]


# Web UI uses this to replace stale sector topics in localStorage. Increment **every** time
# you add/remove/reorder/edit entries in any sector's topic list.
SECTOR_TOPICS_REVISION: int = 1


def safe_sector_topics_revision() -> int:
    """Return ``SECTOR_TOPICS_REVISION`` as an int >= 1 for API consumers."""
    try:
        revision = int(SECTOR_TOPICS_REVISION)
    except (TypeError, ValueError):
        return 1
    return revision if revision >= 1 else 1


# ── ENERGY ───────────────────────────────────────────────────────────────────
# Desk-specific guidance for AI query expansion. A generic "reword this query" prompt
# produces synonym swaps; naming the desk's benchmarks, venues and units makes the
# variations retrieve genuinely different documents instead of near-duplicates.
ENERGY_EXPANSION_PROMPT: str = """You are a crude oil and refined products desk analyst writing search \
queries for a real-time news feed.

Useful vocabulary for this desk: Brent, WTI, Dubai and Murban benchmarks; OPEC+ quotas, compliance and \
spare capacity; contango, backwardation, time spreads and the forward curve; crack spreads, distillate \
and gasoline cracks; refinery turnarounds, run cuts and utilisation rates; VLCC, Suezmax and Aframax \
freight rates and tanker day rates; the Strait of Hormuz, Red Sea, Bab el-Mandeb, Suez and Panama \
canals; EIA, IEA and OPEC monthly reports and inventory draws or builds at Cushing and the ARA hub; \
LNG cargoes, TTF and Henry Hub, JKM and regasification; sanctions, price caps, shadow fleet and \
ship-to-ship transfers; FIDs, licensing rounds, upstream capex and decline rates.

When generating variations:
- Shift the angle rather than only swapping synonyms: move between price action, physical flows, \
policy decisions, positioning and company or trader commentary
- Prefer the specific benchmark, region, grade, hub or institution over generic wording
- Keep each variation a self-contained search query about the sector, never about one named company"""


# Google-style phrasing: keyword-dense natural language, no company placeholder.
ENERGY_TOPICS: list[SectorTopic] = [
    {
        "topic_name": "Crude Prices",
        "topic_text": "Brent and WTI crude oil prices rise or fall on shifting supply and demand outlook",
    },
    {
        "topic_name": "OPEC+ Policy",
        "topic_text": "OPEC+ ministers agree to raise cut or extend crude production quotas",
    },
    {
        "topic_name": "Supply Disruption",
        "topic_text": "unplanned oil field outage pipeline shutdown or export terminal disruption halts crude supply",
    },
    {
        "topic_name": "Inventories",
        "topic_text": "weekly US crude oil and gasoline inventories build or draw in EIA petroleum status report",
    },
    {
        "topic_name": "Refining",
        "topic_text": "refinery outage maintenance turnaround or unplanned shutdown tightens refined product supply",
    },
    {
        "topic_name": "Product Cracks",
        "topic_text": "diesel gasoline and jet fuel crack spreads and distillate stock levels move on demand",
    },
    {
        "topic_name": "Sanctions",
        "topic_text": "sanctions on Russian and Iranian crude exports price cap enforcement and shadow fleet tankers",
    },
    {
        "topic_name": "Geopolitical Risk",
        "topic_text": "Middle East conflict Strait of Hormuz and Red Sea attacks threaten tanker traffic and oil flows",
    },
    {
        "topic_name": "Demand Outlook",
        "topic_text": "IEA OPEC and EIA revise global oil demand growth forecasts for the year",
    },
    {
        "topic_name": "Freight and Tankers",
        "topic_text": "crude tanker freight rates and VLCC earnings surge as shipping routes shift",
    },
    {
        "topic_name": "Gas and LNG",
        "topic_text": "European TTF and US Henry Hub natural gas prices move on LNG cargo flows and storage levels",
    },
    {
        "topic_name": "Positioning",
        "topic_text": "hedge funds and managed money shift net length in crude futures as the curve moves into contango or backwardation",
    },
    {
        "topic_name": "Upstream Investment",
        "topic_text": "upstream capital spending licensing round and final investment decision on new oil and gas project",
    },
    {
        "topic_name": "Weather Outages",
        "topic_text": "hurricane or extreme cold disrupts Gulf of Mexico oil production and Gulf Coast refining",
    },
    {
        "topic_name": "Policy and Transition",
        "topic_text": "government energy policy emissions rules and transition targets reshape oil and gas investment",
    },
]


# Ordered registry driving the sector tile grid. Disabled sectors render as
# "coming soon" tiles and carry no topics.
SECTORS: list[Sector] = [
    {
        "id": "energy",
        "label": "Energy",
        "description": "Crude, refined products, gas and LNG, freight and policy",
        "enabled": True,
        "topics": ENERGY_TOPICS,
        "expansion_prompt": ENERGY_EXPANSION_PROMPT,
    },
    {
        "id": "metals_mining",
        "label": "Metals & Mining",
        "description": "Base and precious metals, mine supply and processing",
        "enabled": False,
        "topics": [],
        "expansion_prompt": "",
    },
    {
        "id": "utilities_power",
        "label": "Utilities & Power",
        "description": "Power prices, grid capacity and generation mix",
        "enabled": False,
        "topics": [],
        "expansion_prompt": "",
    },
    {
        "id": "shipping_freight",
        "label": "Shipping & Freight",
        "description": "Dry bulk, container rates and trade route shifts",
        "enabled": False,
        "topics": [],
        "expansion_prompt": "",
    },
]


class UnknownSectorError(ValueError):
    """Raised when a sector id is unknown or not enabled for search."""


def get_sector(sector_id: str) -> Sector:
    """
    Look up an enabled sector by id.

    Args:
        sector_id: Sector identifier (case-insensitive), e.g. ``"energy"``

    Returns:
        The sector definition including its topic list

    Raises:
        UnknownSectorError: If the id is unknown or the sector is not enabled
    """
    key = sector_id.strip().lower()
    for sector in SECTORS:
        if sector["id"] == key:
            if not sector["enabled"]:
                raise UnknownSectorError(f"Sector '{sector_id}' is not available yet")
            return sector

    available = ", ".join(s["id"] for s in SECTORS if s["enabled"])
    raise UnknownSectorError(f"Unknown sector '{sector_id}'. Available: {available}")


def get_sector_expansion_prompt(sector_id: str) -> str:
    """
    Return the AI query-expansion prompt for a sector.

    Falls back to a generic sector prompt so expansion still works for a sector that
    has topics but no bespoke desk guidance yet.

    Args:
        sector_id: Sector identifier (case-insensitive)

    Raises:
        UnknownSectorError: If the id is unknown or the sector is not enabled
    """
    sector = get_sector(sector_id)
    prompt = (sector.get("expansion_prompt") or "").strip()
    if prompt:
        return prompt

    return (
        f"You are a {sector['label']} sector analyst writing search queries for a real-time news feed. "
        "Shift the angle of each variation rather than only swapping synonyms, prefer specific "
        "benchmarks, regions and institutions over generic wording, and keep every variation a "
        "self-contained query about the sector rather than about one named company."
    )


def list_sectors() -> list[Sector]:
    """Return tile metadata for every sector, with topic counts instead of payloads."""
    return [
        {
            "id": sector["id"],
            "label": sector["label"],
            "description": sector["description"],
            "enabled": sector["enabled"],
            "topic_count": len(sector["topics"]),
        }
        for sector in SECTORS
    ]


def default_topics_by_sector() -> dict[str, list[SectorTopic]]:
    """Return default topic lists keyed by sector id (enabled sectors only)."""
    return {sector["id"]: sector["topics"] for sector in SECTORS if sector["enabled"]}

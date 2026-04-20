"""
Topic templates and search configuration for news searches
Each topic is formatted with {company} placeholder for company name
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SearchConfig:
    """Configuration for topic-based news searches"""
    
    # Search options
    baseline_enabled: bool = True   # Enable baseline company-only search
    topics_enabled: bool = True     # Enable topic-based searches
    
    # Time range
    days_lookback: int = 7  # How many days back to search
    
    # Sentiment filters
    sentiment_enabled: bool = True  # Enable sentiment filtering for topics
    sentiment_values: List[str] = None  # ["positive", "negative"] excludes neutral
    
    # Document types
    document_types: List[str] = None  # ["NEWS", "TRANSCRIPT", "PRESS_RELEASE", etc.]
    
    # Relevance settings
    min_relevance_baseline: float = 0.0  # Minimum relevance for baseline results
    min_relevance_topics: float = 0.0    # Minimum relevance for topic results
    rerank_threshold: Optional[float] = None  # Rerank threshold for API
    
    # Result limits
    max_chunks_baseline: int = 100  # Max chunks for baseline search
    max_chunks_topics: int = 10      # Max chunks per topic search
    max_results_per_topic: Optional[int] = None  # Limit results per topic
    
    # Parallel execution
    batch_size: int = 50  # Number of concurrent topic searches
    
    # Rate limiting
    rate_limit_rpm: int = 200  # Requests per minute
    
    # Caching
    cache_ttl_hours: int = 24  # Cache TTL for company data
    
    def __post_init__(self):
        """Set default values for None fields"""
        if self.sentiment_values is None:
            self.sentiment_values = ["positive", "negative"]
        if self.document_types is None:
            self.document_types = ["NEWS", "TRANSCRIPT"]


# Default configuration (current production settings)
DEFAULT_CONFIG = SearchConfig(
    baseline_enabled=False,       # Topics only by default
    topics_enabled=True,
    days_lookback=7,
    sentiment_enabled=True,
    sentiment_values=["positive", "negative"],
    document_types=["NEWS", "TRANSCRIPT"],
    min_relevance_baseline=0.0,
    min_relevance_topics=0.0,
    rerank_threshold=None,
    max_chunks_baseline=100,
    max_chunks_topics=10,
    batch_size=50,
    rate_limit_rpm=500,
    cache_ttl_hours=24,
)

# Aggressive configuration (stricter filters, higher quality)
AGGRESSIVE_CONFIG = SearchConfig(
    baseline_enabled=False,       # Topics only
    topics_enabled=True,
    days_lookback=7,
    sentiment_enabled=True,
    sentiment_values=["positive", "negative"],
    document_types=["NEWS", "TRANSCRIPT"],
    min_relevance_baseline=0.5,  # Only high-relevance baseline articles
    min_relevance_topics=0.6,     # Only very relevant topic articles
    rerank_threshold=0.3,         # Enable reranking
    max_chunks_baseline=50,       # Fewer chunks = faster
    max_chunks_topics=5,          # Very selective
    batch_size=50,
    rate_limit_rpm=500,
    cache_ttl_hours=24,
)

# Comprehensive configuration (more results, all sentiment)
COMPREHENSIVE_CONFIG = SearchConfig(
    baseline_enabled=False,       # Topics only
    topics_enabled=True,
    days_lookback=14,             # Look back 2 weeks
    sentiment_enabled=False,      # Include all sentiment (even neutral)
    sentiment_values=None,        # Not used when disabled
    document_types=["NEWS", "TRANSCRIPT", "PRESS_RELEASE"],
    min_relevance_baseline=0.0,
    min_relevance_topics=0.0,
    rerank_threshold=None,
    max_chunks_baseline=200,      # More chunks
    max_chunks_topics=20,         # More chunks per topic
    batch_size=50,
    rate_limit_rpm=500,
    cache_ttl_hours=24,
)

# Fast configuration (speed-optimized)
FAST_CONFIG = SearchConfig(
    baseline_enabled=False,       # Topics only
    topics_enabled=True,
    days_lookback=3,              # Only last 3 days
    sentiment_enabled=True,
    sentiment_values=["positive", "negative"],
    document_types=["NEWS"],      # News only (faster)
    min_relevance_baseline=0.3,   # Skip low-relevance
    min_relevance_topics=0.4,
    rerank_threshold=None,
    max_chunks_baseline=30,       # Fewer chunks
    max_chunks_topics=3,          # Very few per topic
    batch_size=50,
    rate_limit_rpm=500,
    cache_ttl_hours=24,
)

# Breaking news configuration (recent only, all sentiment)
BREAKING_NEWS_CONFIG = SearchConfig(
    baseline_enabled=False,       # Topics only
    topics_enabled=True,
    days_lookback=1,              # Only today
    sentiment_enabled=False,      # All sentiment (breaking news is breaking)
    sentiment_values=None,
    document_types=["NEWS", "PRESS_RELEASE"],
    min_relevance_baseline=0.0,
    min_relevance_topics=0.0,
    rerank_threshold=None,
    max_chunks_baseline=50,
    max_chunks_topics=5,
    batch_size=50,
    rate_limit_rpm=500,
    cache_ttl_hours=1,            # Short cache for breaking news
)

# Topics only configuration (no baseline search)
TOPICS_ONLY_CONFIG = SearchConfig(
    baseline_enabled=False,       # Skip baseline search
    topics_enabled=True,          # Only topic searches
    days_lookback=7,
    sentiment_enabled=True,
    sentiment_values=["positive", "negative"],
    document_types=["NEWS", "TRANSCRIPT"],
    min_relevance_baseline=0.0,
    min_relevance_topics=0.0,
    rerank_threshold=None,
    max_chunks_baseline=0,        # Not used
    max_chunks_topics=10,
    batch_size=50,
    rate_limit_rpm=500,
    cache_ttl_hours=24,
)


# Baseline only configuration (entity search only, no topics)
BASELINE_ONLY_CONFIG = SearchConfig(
    baseline_enabled=True,        # Run baseline search
    topics_enabled=False,         # Skip topic searches
    days_lookback=7,
    sentiment_enabled=False,      # No sentiment filter for basic search
    sentiment_values=None,
    document_types=["NEWS", "TRANSCRIPT"],
    min_relevance_baseline=0.0,
    min_relevance_topics=0.0,     # Not used
    rerank_threshold=None,
    max_chunks_baseline=100,      # All chunks for baseline
    max_chunks_topics=0,          # Not used
    batch_size=50,
    rate_limit_rpm=500,
    cache_ttl_hours=24,
)


# Web UI uses this to replace stale topics in localStorage. Increment **every** time you
# add/remove/reorder/edit entries in DEFAULT_TOPICS (not only when changing categories).
DEFAULT_TOPICS_REVISION: int = 2


def safe_default_topics_revision() -> int:
    """Return ``DEFAULT_TOPICS_REVISION`` as an int >= 1 for API consumers."""
    try:
        r = int(DEFAULT_TOPICS_REVISION)
    except (TypeError, ValueError):
        return 1
    return r if r >= 1 else 1


DEFAULT_TOPICS = [

    # ── FINANCIAL METRICS ────────────────────────────────────────────────
    {"topic_name": "Financial Metrics",
     "topic_text": "{company} reported earnings results beating or missing revenue and profit expectations"},
    {"topic_name": "Financial Metrics",
     "topic_text": "{company} announced changes to full year financial guidance or operational outlook"},
    {"topic_name": "Financial Metrics",
     "topic_text": "{company} showing notable improvement or deterioration in margins revenue or profitability"},

    # ── M&A ──────────────────────────────────────────────────────────────
    {"topic_name": "M&A",
     "topic_text": "{company} agreed to acquire a company for billions in a cash or stock deal"},
    {"topic_name": "M&A",
     "topic_text": "{company} selling divesting or spinning off a business unit or subsidiary"},
    {"topic_name": "M&A",
     "topic_text": "{company} announced a major strategic partnership or joint venture with another company"},

    # ── LEADERSHIP ───────────────────────────────────────────────────────
    {"topic_name": "Leadership",
     "topic_text": "{company} names new chief executive or top executive steps down from role"},
    {"topic_name": "Leadership",
     "topic_text": "{company} leadership transition as longtime executive departs or senior management reshuffled"},

    # ── COMPETITION ──────────────────────────────────────────────────────
    {"topic_name": "Competition",
     "topic_text": "{company} won or lost a significant customer contract or renewed a major deal"},
    {"topic_name": "Competition",
     "topic_text": "{company} losing or gaining market share to competitors in its core business"},
    {"topic_name": "Competition",
     "topic_text": "{company} responding to new competitive threat or disruptive market entrant"},

    # ── PRODUCTS ─────────────────────────────────────────────────────────
    {"topic_name": "Products",
     "topic_text": "{company} launched a new product service or announced a significant pipeline development"},

    # ── SUPPLY CHAIN ─────────────────────────────────────────────────────
    {"topic_name": "Supply Chain",
     "topic_text": "{company} experiencing operational disruptions capacity constraints or logistics challenges"},
    {"topic_name": "Supply Chain",
     "topic_text": "supply chain disruptions or input shortages affecting {company} production and margins"},
    {"topic_name": "Supply Chain",
     "topic_text": "{company} achieved production milestone or announced manufacturing efficiency improvement"},

    # ── COSTS ────────────────────────────────────────────────────────────
    {"topic_name": "Costs",
     "topic_text": "{company} announced cost cutting restructuring layoffs or expense reduction program"},

    # ── REGULATORY ───────────────────────────────────────────────────────
    {"topic_name": "Regulatory",
     "topic_text": "new regulation or government policy materially affecting {company} business or compliance costs"},
    {"topic_name": "Regulatory",
     "topic_text": "{company} facing material litigation legal judgment or adverse court ruling"},

    # ── INDUSTRY ─────────────────────────────────────────────────────────
    {"topic_name": "Industry",
     "topic_text": "macroeconomic headwinds or tailwinds from interest rates inflation or consumer demand affecting {company}"},
    {"topic_name": "Industry",
     "topic_text": "structural industry shift or sector disruption directly impacting {company} competitive position"},

    # ── FINANCING ────────────────────────────────────────────────────────
    {"topic_name": "Financing",
     "topic_text": "{company} announced share buyback dividend increase capital raise or major capital allocation decision"},
    {"topic_name": "Financing",
     "topic_text": "{company} increased reduced or suspended dividend or shareholder return program"},
    {"topic_name": "Financing",
     "topic_text": "{company} raised capital through new bond offering or senior notes issuance"},
    {"topic_name": "Financing",
     "topic_text": "{company} refinanced its debt or extended maturity on existing credit facilities"},
    {"topic_name": "Financing",
     "topic_text": "{company} credit rating upgraded downgraded or placed on outlook watch by rating agency"},

    # ── MARKETS ──────────────────────────────────────────────────────────
    {"topic_name": "Markets",
     "topic_text": "institutional investors or analysts shifting sentiment on {company} outlook or valuation"},
    {"topic_name": "Markets",
     "topic_text": "upcoming catalyst event risk or macro development that could move {company} stock"},
    {"topic_name": "Markets",
     "topic_text": "{company} made an unexpected disclosure or is subject to unusual trading activity or short interest"},
    {"topic_name": "Markets",
     "topic_text": "activist investor building stake in {company} or pushing for strategic or governance changes"},
]

# Topic categories for grouping (indices align with DEFAULT_TOPICS order)
TOPIC_CATEGORIES = {
    "financial_metrics": [0, 1, 2],
    "ma": [3, 4, 5],
    "leadership": [6, 7],
    "competition": [8, 9, 10],
    "products": [11],
    "supply_chain": [12, 13, 14],
    "costs": [15],
    "regulatory": [16, 17],
    "industry": [18, 19],
    "financing": [20, 21, 22, 23, 24],
    "markets": [25, 26, 27, 28],
}

# Pre-refactor ``get_topic_category`` / TOPIC_CATEGORIES keys (different index layout).
# Use ``normalize_topic_category_slug`` if you persist old slugs in tools or dashboards.
TOPIC_CATEGORY_LEGACY_SLUGS: dict[str, str] = {
    "earnings": "financial_metrics",
    "strategy": "ma",
    "leadership": "leadership",
    "commercial": "competition",
    "products": "products",
    "operations": "supply_chain",
    "costs": "costs",
    "regulatory": "regulatory",
    "macro": "industry",
    "capital": "financing",
    "sentiment": "markets",
}


def normalize_topic_category_slug(slug: str) -> str:
    """Map legacy category slugs to current ``TOPIC_CATEGORIES`` keys (case-insensitive)."""
    key = slug.strip().lower()
    return TOPIC_CATEGORY_LEGACY_SLUGS.get(key, key)


def get_topic_category(topic_index: int) -> str:
    """
    Get category slug for a topic index (matches keys in TOPIC_CATEGORIES).

    If you stored older slugs (e.g. ``earnings``, ``capital``), pass them through
    :func:`normalize_topic_category_slug`.

    Args:
        topic_index: Index of topic in DEFAULT_TOPICS list

    Returns:
        Category slug or "uncategorized"
    """
    for category, indices in TOPIC_CATEGORIES.items():
        if topic_index in indices:
            return category
    return "uncategorized"


def get_config_by_name(name: str) -> SearchConfig:
    """
    Get a predefined configuration by name.
    
    Args:
        name: Configuration name (default, aggressive, comprehensive, fast, breaking_news, topics_only, baseline_only)
        
    Returns:
        SearchConfig instance
        
    Raises:
        ValueError: If configuration name not found
    """
    configs = {
        "default": DEFAULT_CONFIG,
        "aggressive": AGGRESSIVE_CONFIG,
        "comprehensive": COMPREHENSIVE_CONFIG,
        "fast": FAST_CONFIG,
        "breaking_news": BREAKING_NEWS_CONFIG,
        "topics_only": TOPICS_ONLY_CONFIG,
        "baseline_only": BASELINE_ONLY_CONFIG,
    }
    
    name_lower = name.lower()
    if name_lower not in configs:
        available = ", ".join(configs.keys())
        raise ValueError(f"Unknown config '{name}'. Available: {available}")
    
    return configs[name_lower]


def list_available_configs() -> dict:
    """
    Get all available configurations with descriptions.
    
    Returns:
        Dictionary of config_name -> description
    """
    return {
        "default": "Topic search (7 days, sentiment filtered, no baseline)",
        "aggressive": "Topic search with strict quality filters (high relevance only)",
        "comprehensive": "Topic search with max coverage (14 days, all sentiment)",
        "fast": "Topic search, speed-optimized (3 days, fewer chunks)",
        "breaking_news": "Topic search, recent only (1 day, all sentiment)",
        "topics_only": "Topic searches only (no baseline search)",
        "baseline_only": "Entity search only (no topic searches, no sentiment filter)",
    }


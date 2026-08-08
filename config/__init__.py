"""
Configuration module
"""

from .sector_topics import (
    ENERGY_TOPICS,
    SECTORS,
    UnknownSectorError,
    default_topics_by_sector,
    get_sector,
    get_sector_expansion_prompt,
    list_sectors,
    safe_sector_topics_revision,
)
from .topics import (
    DEFAULT_TOPICS,
    NEGATIVE_NEWS_CATEGORIES,
    SEARCH_SOURCE_CATEGORIES,
    normalize_topic_category_slug,
    safe_default_topics_revision,
    safe_negative_news_categories_revision,
)

__all__ = [
    "DEFAULT_TOPICS",
    "ENERGY_TOPICS",
    "NEGATIVE_NEWS_CATEGORIES",
    "SEARCH_SOURCE_CATEGORIES",
    "SECTORS",
    "UnknownSectorError",
    "default_topics_by_sector",
    "get_sector",
    "get_sector_expansion_prompt",
    "list_sectors",
    "normalize_topic_category_slug",
    "safe_default_topics_revision",
    "safe_negative_news_categories_revision",
    "safe_sector_topics_revision",
]

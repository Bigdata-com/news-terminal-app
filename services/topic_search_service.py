"""
Topic-based news search service using Bigdata.com API.

This module provides asynchronous news search capabilities with separate methods
for baseline (entity-only) and topic (sentiment-filtered) searches.

KEY CLASSES:
    TopicSearchService: Main service class for news searches

KEY PUBLIC METHODS:
    search_ticker(): Topic-based search for a single ticker (parallel topics)
    search_multiple_tickers(): Topic searches for multiple tickers in parallel
    search_baseline(): Entity-filtered search (no topics, no sentiment filter)
    search_single_topic(): Single topic search with sentiment filter
    search_sector(): Theme-based search for a sector (parallel topics, no entity filter)
    search_single_theme(): Single theme search with no entity filter
    get_company_data(): Resolve ticker to entity ID via Knowledge Graph API
    generate_topic_variations(): Generate 3 query variations using Gemini AI
    generate_theme_variations(): Generate 3 sector query variations using a per-sector prompt
    close(): Clean up HTTP session

FEATURES:
    - Parallel execution of multiple topic searches (async/await)
    - Query reformulation using Gemini AI (optional, generates 3 variations per topic)
    - Smart rate limiting (500 RPM across all requests)
    - Company data caching (entity IDs, 24hr TTL)
    - Multi-level deduplication (within searches and across topics)
    - Shared HTTP session for connection pooling (faster performance)
    - Configurable chunk budgets (default: 100 total chunks per search)
    - Relevance-based filtering and best-chunk selection

USAGE EXAMPLES:
    service = TopicSearchService(api_key="your-key")
    
    # Baseline search (entity filter only, no sentiment)
    baseline_results = await service.search_baseline("AAPL", entity_id, days=7)
    
    # Topic search (sentiment-filtered parallel topic searches)
    topic_results = await service.search_ticker("AAPL", days=7)
    
    # Topic search with query reformulation (4x searches per topic: original + 3 variations)
    topic_results = await service.search_ticker("AAPL", days=7, query_reformulation=True)
    
    # Multiple tickers (topic search)
    all_results = await service.search_multiple_tickers(["AAPL", "GOOGL"], days=7)
    
    # Sector search (theme queries, no company involved)
    sector_results = await service.search_sector("energy", ENERGY_TOPICS, days=7)
    
    await service.close()
"""

import asyncio
import aiohttp
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
import logging
from pydantic import BaseModel

from .rate_limiter import RateLimiter
from .company_cache import CompanyDataCache, CompanyData
from .gemini_service import GeminiService
from config.topics import (
    DEFAULT_TOPICS,
    NEGATIVE_NEWS_CATEGORIES,
    NEGATIVE_NEWS_ENTITY_BATCH_SIZE,
    NEGATIVE_NEWS_ENTITY_SEARCH_IN,
    NEGATIVE_NEWS_SENTIMENT_RANGES,
)

logger = logging.getLogger(__name__)

# Total chunks requested per search, divided across all queries in that search
TOTAL_CHUNK_BUDGET = 300


class TopicVariations(BaseModel):
    """Pydantic model for topic variations from Gemini."""
    variation_1: str
    variation_2: str
    variation_3: str


class TopicSearchService:
    """
    Service for performing topic-based news searches.
    
    Features:
    - Optional baseline entity-only search (no sentiment filter)
    - Parallel topic searches (one API call per topic template; sentiment filter on topic queries)
    - Rate limiting to respect 500 RPM API limit
    - Caching of company data (entity IDs and names)
    - Shared HTTP session for connection pooling (much faster!)
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.bigdata.com/v1",
        rate_limiter: Optional[RateLimiter] = None,
        company_cache: Optional[CompanyDataCache] = None,
        gemini_service: Optional[GeminiService] = None,
    ):
        """
        Initialize topic search service.
        
        Args:
            api_key: Bigdata.com API key
            base_url: Base URL for Bigdata API
            rate_limiter: Rate limiter instance (creates new if None)
            company_cache: Company cache instance (creates new if None)
            gemini_service: Gemini service instance for query reformulation (creates new if None)
        """
        self.api_key = api_key
        self.base_url = base_url
        self.rate_limiter = rate_limiter or RateLimiter(max_tokens=200, refill_period=60)
        self.company_cache = company_cache or CompanyDataCache(ttl_hours=24)
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Initialize Gemini service for query reformulation (lazy init)
        self._gemini_service = gemini_service
        
        logger.info("TopicSearchService initialized")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create shared aiohttp session.
        Reuses connection pool for much better performance.
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    def _get_gemini_service(self) -> GeminiService:
        """
        Get or create Gemini service instance (lazy initialization).
        Only creates if query reformulation is used.
        """
        if self._gemini_service is None:
            try:
                # Try to initialize with automatic detection (supports both Vertex AI and API key)
                self._gemini_service = GeminiService()
                logger.info(
                    f"GeminiService initialized for query reformulation "
                    f"(auth method: {self._gemini_service.auth_method})"
                )
            except ValueError as e:
                logger.error(f"Failed to initialize GeminiService: {e}")
                raise ValueError(
                    "Query reformulation requires Gemini auth. Configure one of:\n"
                    "  1. Vertex: GOOGLE_GENAI_USE_VERTEXAI=true, GOOGLE_CLOUD_PROJECT, and either "
                    "GOOGLE_APPLICATION_CREDENTIALS (JSON) or Application Default Credentials "
                    "(e.g. gcloud auth application-default login), or\n"
                    "  2. AI Studio: GEMINI_API_KEY (with Vertex env vars unset or false).\n"
                    "Or disable query reformulation."
                ) from e
        return self._gemini_service
    
    async def generate_topic_variations(
        self,
        topic,  # Can be str or dict with topic_text
        company_name: str
    ) -> List[str]:
        """
        Generate 3 variations of a topic query using Gemini AI.
        
        Args:
            topic: Original topic query template (may contain {company} placeholder)
                  Can be either a string or a dict with 'topic_text' key
            company_name: Company name to substitute in the template
            
        Returns:
            List of 3 topic variations
        """
        # Handle both dict and string topic formats
        if isinstance(topic, dict):
            topic_text = topic.get("topic_text", "")
        else:
            topic_text = topic
        
        # Format the topic with company name first
        formatted_topic = topic_text.format(company=company_name) if "{company}" in topic_text else topic_text
        
        prompt = f"""You are a financial news search expert. Given this search query about a company:

"{formatted_topic}"

Generate 3 alternative search queries that would find similar or related news articles. The variations should:
- Maintain the core intent and meaning
- Use different wording or phrasing
- Cover slightly different angles of the same topic
- Be suitable for semantic search (not keyword search)
- Stay focused on financial/business news context

Return exactly 3 variations, each as a complete search query."""

        try:
            gemini = self._get_gemini_service()
            variations = await gemini.generate_content(
                prompt=prompt,
                response_schema=TopicVariations
            )
            
            result = [
                variations.variation_1,
                variations.variation_2,
                variations.variation_3
            ]
            
            # Log original and variations (truncated for readability)
            logger.info(f"Query Reformulation Generated:")
            logger.info(f"  Original: {formatted_topic[:80]}{'...' if len(formatted_topic) > 80 else ''}")
            for i, var in enumerate(result, 1):
                logger.info(f"  Variation {i}: {var[:80]}{'...' if len(var) > 80 else ''}")
            
            return result
            
        except Exception as e:
            logger.warning(f"Failed to generate topic variations: {e}. Using original topic only.")
            # Return empty list on failure - caller will use original topic only
            return []
    
    async def generate_theme_variations(
        self,
        topic,  # Can be str or dict with topic_text
        expansion_prompt: str
    ) -> List[str]:
        """
        Generate 3 variations of a sector theme query using Gemini AI.
        
        Unlike :meth:`generate_topic_variations`, there is no company to substitute, and the
        desk-specific guidance comes from the sector's own ``expansion_prompt`` so variations
        use that market's vocabulary instead of generic financial wording.
        
        Args:
            topic: Theme phrase, or dict with a 'topic_text' key
            expansion_prompt: Sector-specific instructions from config/sector_topics.py
            
        Returns:
            List of 3 theme variations, or an empty list if generation fails
        """
        if isinstance(topic, dict):
            topic_text = topic.get("topic_text", "")
        else:
            topic_text = topic
        
        topic_text = topic_text.strip()
        if not topic_text:
            return []
        
        prompt = f"""{expansion_prompt}

Original search query:
"{topic_text}"

Generate 3 alternative search queries that would surface additional relevant articles for this desk. \
Each variation must:
- Keep the core intent of the original query
- Approach it from a different angle rather than only swapping synonyms
- Read as natural language suitable for semantic search, not a keyword list
- Contain no placeholders and no single company as its subject

Return exactly 3 variations, each as a complete search query."""
        
        try:
            gemini = self._get_gemini_service()
            variations = await gemini.generate_content(
                prompt=prompt,
                response_schema=TopicVariations
            )
            
            result = [
                variations.variation_1,
                variations.variation_2,
                variations.variation_3
            ]
            
            logger.info("Theme Query Expansion Generated:")
            logger.info(f"  Original: {topic_text[:80]}{'...' if len(topic_text) > 80 else ''}")
            for i, var in enumerate(result, 1):
                logger.info(f"  Variation {i}: {var[:80]}{'...' if len(var) > 80 else ''}")
            
            return result
            
        except Exception as e:
            logger.warning(f"Failed to generate theme variations: {e}. Using original phrase only.")
            return []
    
    async def close(self):
        """Close the shared HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("HTTP session closed")
    
    def _format_timestamp(self, dt: datetime) -> str:
        """Format datetime to ISO 8601 with milliseconds and Z suffix."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        
        iso_str = dt.strftime('%Y-%m-%dT%H:%M:%S')
        milliseconds = dt.microsecond // 1000
        return f"{iso_str}.{milliseconds:03d}Z"
    
    def _get_time_ago(self, timestamp_str: str) -> str:
        """Convert timestamp string to human-readable time ago."""
        try:
            # Parse ISO format timestamp (handle both with and without Z)
            if timestamp_str.endswith('Z'):
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            elif '+' in timestamp_str or timestamp_str.count('-') > 2:
                timestamp = datetime.fromisoformat(timestamp_str)
            else:
                # Assume UTC if no timezone
                timestamp = datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            diff = now - timestamp
            
            if diff.days > 0:
                return f"{diff.days}d ago"
            elif diff.seconds >= 3600:
                hours = diff.seconds // 3600
                return f"{hours}h ago"
            elif diff.seconds >= 60:
                minutes = diff.seconds // 60
                return f"{minutes}m ago"
            else:
                return "Just now"
        except Exception as e:
            logger.warning(f"Error parsing timestamp '{timestamp_str}': {e}")
            return "Unknown time"
    
    def _deduplicate_by_document_id(self, results: List[Dict]) -> List[Dict]:
        """
        Deduplicate results by document ID, keeping the chunk with highest relevance.
        
        The API can return the same document multiple times with different chunks.
        We keep only one instance per document ID - the one with the best chunk.
        
        Args:
            results: List of raw API results (each has id and chunks)
            
        Returns:
            Deduplicated list with one entry per document ID
        """
        # Group by document ID
        doc_groups = {}
        
        for article in results:
            doc_id = article.get("id")
            if not doc_id:
                continue
            
            chunks = article.get("chunks", [])
            if not chunks:
                continue
            
            # Find the best chunk for this article instance
            sorted_chunks = sorted(chunks, key=lambda x: x.get("relevance", 0), reverse=True)
            best_chunk = sorted_chunks[0]
            
            # If we haven't seen this document, or this chunk is better, keep it
            if doc_id not in doc_groups or best_chunk.get("relevance", 0) > doc_groups[doc_id]["best_relevance"]:
                doc_groups[doc_id] = {
                    "article": article,
                    "best_chunk": best_chunk,
                    "best_relevance": best_chunk.get("relevance", 0)
                }
        
        # Return deduplicated list
        deduplicated = [
            {
                "article": data["article"],
                "best_chunk": data["best_chunk"],
                "relevance": data["best_relevance"]
            }
            for data in doc_groups.values()
        ]
        
        logger.debug(
            f"Deduplication: {len(results)} raw results -> {len(deduplicated)} unique documents"
        )
        
        return deduplicated
    
    def _deduplicate_across_topics(self, topic_results: List[Dict]) -> List[Dict]:
        """
        Deduplicate topic results when same article appears in multiple topics.
        Keep the version with highest relevance score.
        
        Args:
            topic_results: List of formatted article dictionaries from multiple topics
            
        Returns:
            Deduplicated list with one entry per document ID
        """
        doc_map = {}
        
        for article in topic_results:
            doc_id = article.get("id")
            if not doc_id:
                continue
            
            relevance = article.get("relevance", 0)
            
            # Keep the version with highest relevance
            if doc_id not in doc_map or relevance > doc_map[doc_id].get("relevance", 0):
                doc_map[doc_id] = article
        
        return list(doc_map.values())
    
    def _build_filters(
        self,
        days: float,
        entity_id: Optional[str] = None,
        sentiment: bool = False,
        document_types: Optional[List[str]] = None,
    ) -> Dict:
        """
        Build the ``query.filters`` block for a /search request.

        Omitting ``entity_id`` produces a theme (sector) query that is not scoped to
        any company, which is what sector searches rely on.

        Args:
            days: Lookback window in days (fractional values allowed)
            entity_id: Bigdata entity ID to scope the search to, or None for theme search
            sentiment: If True, exclude neutral chunks (positive/negative only)
            document_types: Document types to include (defaults to NEWS + TRANSCRIPT)

        Returns:
            Filters dictionary ready to embed in the request body
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)

        filters: Dict = {
            "timestamp": {
                "start": self._format_timestamp(start_time),
                "end": self._format_timestamp(end_time)
            },
            "document_type": {
                "mode": "INCLUDE",
                "values": document_types or ["NEWS", "TRANSCRIPT"]
            }
        }

        if entity_id:
            filters["entity"] = {"all_of": [entity_id]}

        if sentiment:
            filters["sentiment"] = {"values": ["positive", "negative"]}

        return filters

    async def _post_search(
        self,
        text: str,
        filters: Dict,
        max_chunks: int,
        log_label: str,
        error_log_level: int = logging.WARNING,
    ) -> List[Dict]:
        """
        Execute a /search request and return deduplicated ``{article, best_chunk, relevance}`` items.

        Handles rate limiting, transport errors and per-document deduplication so callers
        only deal with formatting. Returns an empty list on any failure.

        Args:
            text: Semantic query text
            filters: Filters block from :meth:`_build_filters`
            max_chunks: Maximum chunks to request
            log_label: Human-readable identifier used in log messages
            error_log_level: Level used for non-200 responses (404 is never logged)

        Returns:
            Deduplicated result items, or an empty list on error
        """
        await self.rate_limiter.acquire()

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/search",
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "query": {
                        "text": text,
                        "filters": filters,
                        "max_chunks": max_chunks
                    }
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])
                    deduplicated = self._deduplicate_by_document_id(results)
                    logger.debug(
                        f"{log_label}: {len(results)} raw results -> {len(deduplicated)} unique documents"
                    )
                    return deduplicated

                if response.status != 404:
                    error_text = await response.text()
                    logger.log(
                        error_log_level,
                        f"Search error for {log_label}: {response.status} - {error_text}"
                    )
                return []

        except asyncio.TimeoutError:
            logger.log(error_log_level, f"Timeout in search for {log_label}")
            return []
        except Exception as e:
            logger.log(error_log_level, f"Error in search for {log_label}: {str(e)}")
            return []

    def _format_article(
        self,
        article: Dict,
        best_chunk: Dict,
        relevance: float,
        fallback_id: str,
        **extra
    ) -> Dict:
        """
        Convert a raw API document plus its best chunk into the article shape used by the UI.

        Args:
            article: Raw document from the API
            best_chunk: Highest-relevance chunk for that document
            relevance: Relevance score of ``best_chunk``
            fallback_id: ID to use when the document has none
            **extra: Search-specific fields (search_type, topic, ticker, sector, ...)

        Returns:
            Article dictionary
        """
        chunk_text = best_chunk.get("text", "")
        summary = chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text
        timestamp = article.get("timestamp", "")

        formatted = {
            "id": article.get("id", fallback_id),
            "headline": article.get("headline", "No headline"),
            "timestamp": timestamp,
            "time_ago": self._get_time_ago(timestamp),
            "source": article.get("source", {}).get("name", "Unknown"),
            "summary": summary,
            "full_text": chunk_text,  # Full chunk text for expanded view
            "document_url": article.get("url"),  # URL to original article (from "url" field)
            "relevance": relevance,
            "document_type": article.get("document_type", "NEWS"),
            "detections": best_chunk.get("detections", []),  # Entity detections from the chunk
        }
        formatted.update(extra)
        return formatted

    async def get_company_data(self, ticker: str) -> Optional[CompanyData]:
        """
        Get company entity ID and name from Knowledge Graph API.
        Uses cache when available.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            CompanyData with entity_id and company_name, or None if not found
        """
        ticker = ticker.upper()
        
        # Check cache first
        cached = self.company_cache.get(ticker)
        if cached:
            return cached
        
        logger.info(f"Fetching company data for {ticker} from Knowledge Graph API")
        
        # Acquire rate limit token
        await self.rate_limiter.acquire()
        
        try:
            session = await self._get_session()
            async with session.post(
                    f"{self.base_url}/knowledge-graph/companies",
                    headers={
                        "X-API-KEY": self.api_key,
                        "Content-Type": "application/json"
                    },
                    json={
                        "query": ticker,
                        "types": ["PUBLIC"]
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        companies = data.get("results", [])
                        
                        if companies:
                            entity_id = companies[0]["id"]
                            company_name = companies[0]["name"]
                            
                            # Cache the result
                            company_data = self.company_cache.set(
                                ticker, entity_id, company_name
                            )
                            
                            logger.info(
                                f"Found company: {company_name} ({ticker}) -> {entity_id}"
                            )
                            return company_data
                        else:
                            logger.warning(f"No companies found for ticker: {ticker}")
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Knowledge Graph API error: {response.status} - {error_text}"
                        )
        
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching company data for {ticker}")
        except Exception as e:
            logger.error(f"Error fetching company data for {ticker}: {str(e)}")
        
        return None
    
    async def search_baseline(
        self,
        ticker: str,
        entity_id: str,
        days: int = 7,
        max_chunks: int = 100
    ) -> List[Dict]:
        """
        Perform baseline company search (no sentiment filter).
        This replicates the original simple search behavior.
        
        Args:
            ticker: Stock ticker symbol
            entity_id: Bigdata entity ID
            days: Number of days to look back
            max_chunks: Maximum chunks to return
            
        Returns:
            List of article dictionaries
        """
        logger.info(f"Running baseline search for {ticker}")
        
        deduplicated = await self._post_search(
            text="earnings financial results stock news",
            filters=self._build_filters(days, entity_id=entity_id),
            max_chunks=max_chunks,
            log_label=f"baseline search for {ticker}",
            error_log_level=logging.ERROR,
        )
        
        articles = [
            self._format_article(
                item["article"],
                item["best_chunk"],
                item["relevance"],
                fallback_id=f"baseline_{i}",
                search_type="baseline",
                topic=None,
                ticker=ticker,
            )
            for i, item in enumerate(deduplicated)
        ]
        
        logger.info(f"Baseline search for {ticker}: {len(articles)} unique articles")
        return articles
    
    async def search_single_topic(
        self,
        ticker: str,
        entity_id: str,
        company_name: str,
        topic: str,
        topic_index: int,
        days: int = 7,
        max_chunks: int = 10
    ) -> List[Dict]:
        """
        Perform topic-based search with sentiment filtering.
        
        Args:
            ticker: Stock ticker symbol
            entity_id: Bigdata entity ID
            company_name: Company name to format topic
            topic: Topic template string or dict with {topic_name, topic_text}
            topic_index: Index of topic in DEFAULT_TOPICS list
            days: Number of days to look back
            max_chunks: Maximum chunks to return
            
        Returns:
            List of article dictionaries tagged with topic
        """
        # Handle both string and dictionary topic formats
        if isinstance(topic, dict):
            topic_name = topic.get("topic_name", f"Topic {topic_index}")
            topic_text = topic.get("topic_text", "")
        else:
            # Legacy string format
            topic_name = f"Topic {topic_index}"
            topic_text = topic
        
        # Format topic with company name
        formatted_topic = topic_text.format(company=company_name)
        
        # Truncate for log readability
        truncated_topic = formatted_topic[:60] + "..." if len(formatted_topic) > 60 else formatted_topic
        logger.debug(f"Searching topic {topic_index} for {ticker}: {truncated_topic}")
        
        deduplicated = await self._post_search(
            text=formatted_topic,
            filters=self._build_filters(days, entity_id=entity_id, sentiment=True),
            max_chunks=max_chunks,
            log_label=f"{ticker} topic {topic_index}",
        )
        
        return [
            self._format_article(
                item["article"],
                item["best_chunk"],
                item["relevance"],
                fallback_id=f"topic_{topic_index}_{i}",
                search_type="topic",
                topic=formatted_topic,
                topic_name=topic_name,
                topic_index=topic_index,
                ticker=ticker,
            )
            for i, item in enumerate(deduplicated)
        ]
    
    async def search_single_theme(
        self,
        topic,
        topic_index: int,
        days: float = 7,
        max_chunks: int = 20,
        sector: Optional[str] = None
    ) -> List[Dict]:
        """
        Perform a theme (sector) search with no entity filter.
        
        Unlike :meth:`search_single_topic`, the phrase is used verbatim: sector topics
        carry no ``{company}`` placeholder because no company is resolved.
        
        Args:
            topic: Topic dict with {topic_name, topic_text}, or a plain phrase string
            topic_index: Index of the topic in the sector's topic list
            days: Number of days to look back
            max_chunks: Maximum chunks to return
            sector: Sector id to tag results with
            
        Returns:
            List of article dictionaries tagged with the topic and sector
        """
        if isinstance(topic, dict):
            topic_name = topic.get("topic_name") or f"Topic {topic_index + 1}"
            topic_text = topic.get("topic_text", "")
        else:
            topic_name = f"Topic {topic_index + 1}"
            topic_text = topic
        
        topic_text = topic_text.strip()
        if not topic_text:
            logger.warning(f"Skipping empty theme topic at index {topic_index}")
            return []
        
        deduplicated = await self._post_search(
            text=topic_text,
            filters=self._build_filters(days, sentiment=True),
            max_chunks=max_chunks,
            log_label=f"{sector or 'sector'} theme {topic_index}",
        )
        
        return [
            self._format_article(
                item["article"],
                item["best_chunk"],
                item["relevance"],
                fallback_id=f"theme_{topic_index}_{i}",
                search_type="theme",
                topic=topic_text,
                topic_name=topic_name,
                topic_index=topic_index,
                sector=sector,
            )
            for i, item in enumerate(deduplicated)
        ]
    
    @staticmethod
    def _chunk_list(items: List, size: int) -> List[List]:
        """Split ``items`` into consecutive batches of at most ``size``."""
        if size < 1:
            size = 1
        return [items[i:i + size] for i in range(0, len(items), size)]

    def _resolve_ticker_from_detections(
        self,
        detections: List[Dict],
        entity_to_ticker: Dict[str, str],
        fallback_ticker: str,
    ) -> str:
        """Map chunk detections to a ticker in the current entity batch."""
        for detection in detections or []:
            entity = detection.get("entity") or {}
            entity_id = entity.get("id") or detection.get("entity_id") or detection.get("id")
            if entity_id and entity_id in entity_to_ticker:
                return entity_to_ticker[entity_id]
        return fallback_ticker

    async def search_negative_category(
        self,
        entity_ids: List[str],
        entity_to_ticker: Dict[str, str],
        category: Dict,
        category_index: int,
        days: int = 7,
        max_chunks: int = 20,
    ) -> List[Dict]:
        """
        Search one negative-news category for a single entity batch.

        Uses filters only (no query text): news_public category, headline entity match,
        strongly negative sentiment range, and taxonomy topic any_of.
        """
        category_name = category.get("category_name", f"Category {category_index}")
        taxonomy_topics = [
            t.strip() for t in (category.get("topics") or []) if isinstance(t, str) and t.strip()
        ]
        if not taxonomy_topics or not entity_ids:
            return []

        if len(entity_ids) > NEGATIVE_NEWS_ENTITY_BATCH_SIZE:
            entity_ids = entity_ids[:NEGATIVE_NEWS_ENTITY_BATCH_SIZE]

        fallback_ticker = entity_to_ticker.get(entity_ids[0], entity_ids[0])
        logger.debug(
            f"Negative search category {category_index} ({category_name}) "
            f"entities={entity_ids}"
        )

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)

        await self.rate_limiter.acquire()

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/search",
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "search_mode": "fast",
                    "query": {
                        "filters": {
                            "timestamp": {
                                "start": self._format_timestamp(start_time),
                                "end": self._format_timestamp(end_time),
                            },
                            "category": {
                                "mode": "INCLUDE",
                                "values": ["news_public"],
                            },
                            "entity": {
                                "search_in": NEGATIVE_NEWS_ENTITY_SEARCH_IN,
                                "any_of": entity_ids,
                            },
                            "sentiment": {
                                "ranges": NEGATIVE_NEWS_SENTIMENT_RANGES,
                            },
                            "topic": {
                                "search_in": "ALL",
                                "any_of": taxonomy_topics,
                            },
                        },
                        "max_chunks": max_chunks,
                    },
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])
                    deduplicated = self._deduplicate_by_document_id(results)

                    articles = []
                    for i, item in enumerate(deduplicated):
                        article = item["article"]
                        best_chunk = item["best_chunk"]
                        relevance = item["relevance"]

                        chunk_text = best_chunk.get("text", "")
                        summary = (
                            chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text
                        )
                        timestamp = article.get("timestamp", "")
                        detections = best_chunk.get("detections", [])
                        ticker = self._resolve_ticker_from_detections(
                            detections, entity_to_ticker, fallback_ticker
                        )

                        articles.append({
                            "id": article.get("id", f"negative_{category_index}_{i}"),
                            "headline": article.get("headline", "No headline"),
                            "timestamp": timestamp,
                            "time_ago": self._get_time_ago(timestamp),
                            "source": article.get("source", {}).get("name", "Unknown"),
                            "summary": summary,
                            "full_text": chunk_text,
                            "document_url": article.get("url"),
                            "relevance": relevance,
                            "document_type": article.get("document_type", "NEWS"),
                            "search_type": "negative",
                            "topic": category_name,
                            "topic_name": category_name,
                            "topic_index": category_index,
                            "ticker": ticker,
                            "detections": detections,
                        })

                    return articles

                if response.status != 404:
                    error_text = await response.text()
                    logger.warning(
                        f"Negative category search error ({category_name}): "
                        f"{response.status} - {error_text}"
                    )
                return []

        except asyncio.TimeoutError:
            logger.warning(f"Timeout in negative category search: {category_name}")
            return []
        except Exception as e:
            logger.warning(f"Error in negative category search ({category_name}): {e}")
            return []

    async def search_negative_news(
        self,
        ticker: str,
        days: int = 7,
        custom_categories: Optional[List[Dict]] = None,
        min_relevance: float = 0.0,
        batch_size: int = 50,
    ) -> Dict:
        """
        Negative-news search for a single ticker (taxonomy topics + negative sentiment).
        """
        ticker = ticker.upper()
        company_data = await self.get_company_data(ticker)
        if not company_data:
            return {
                "ticker": ticker,
                "error": "Company not found",
                "topic_results": [],
                "total_results": 0,
            }

        companies = [
            {
                "ticker": ticker,
                "entity_id": company_data.entity_id,
                "company_name": company_data.company_name,
            }
        ]
        results = await self._search_negative_news_for_companies(
            companies,
            days=days,
            custom_categories=custom_categories,
            min_relevance=min_relevance,
            batch_size=batch_size,
        )
        # Single-ticker response shape matches search_ticker()
        if results:
            return results[0]
        return {
            "ticker": ticker,
            "company_name": company_data.company_name,
            "entity_id": company_data.entity_id,
            "topic_results": [],
            "total_results": 0,
        }

    async def search_negative_news_multiple(
        self,
        tickers: List[str],
        days: int = 7,
        custom_categories: Optional[List[Dict]] = None,
        min_relevance: float = 0.0,
        batch_size: int = 50,
    ) -> List[Dict]:
        """
        Negative-news search for multiple tickers, one entity per search request.
        """
        companies: List[Dict] = []
        unresolved: List[Dict] = []

        for raw in tickers:
            ticker = raw.upper().strip()
            if not ticker:
                continue
            company_data = await self.get_company_data(ticker)
            if not company_data:
                unresolved.append({
                    "ticker": ticker,
                    "error": "Company not found",
                    "topic_results": [],
                    "total_results": 0,
                })
                continue
            companies.append({
                "ticker": ticker,
                "entity_id": company_data.entity_id,
                "company_name": company_data.company_name,
            })

        results = await self._search_negative_news_for_companies(
            companies,
            days=days,
            custom_categories=custom_categories,
            min_relevance=min_relevance,
            batch_size=batch_size,
        )
        return results + unresolved

    async def _search_negative_news_for_companies(
        self,
        companies: List[Dict],
        days: int = 7,
        custom_categories: Optional[List[Dict]] = None,
        min_relevance: float = 0.0,
        batch_size: int = 50,
    ) -> List[Dict]:
        """
        Core negative-news runner: entity batches × categories in parallel.
        """
        start_time = datetime.now()
        categories = custom_categories or NEGATIVE_NEWS_CATEGORIES
        # Normalize / drop empty categories
        categories = [
            {
                "category_name": c.get("category_name", f"Category {i}"),
                "topics": [
                    t.strip()
                    for t in (c.get("topics") or [])
                    if isinstance(t, str) and t.strip()
                ],
            }
            for i, c in enumerate(categories)
            if c.get("topics")
        ]
        categories = [c for c in categories if c["topics"]]

        if not companies or not categories:
            return [
                {
                    "ticker": c["ticker"],
                    "company_name": c.get("company_name"),
                    "entity_id": c.get("entity_id"),
                    "topic_results": [],
                    "total_results": 0,
                    "search_stats": {
                        "categories_searched": 0,
                        "elapsed_seconds": 0,
                        "rate_limiter_stats": self.rate_limiter.get_metrics(),
                    },
                }
                for c in companies
            ]

        entity_batches = self._chunk_list(companies, NEGATIVE_NEWS_ENTITY_BATCH_SIZE)
        total_queries = len(entity_batches) * len(categories)
        total_chunk_budget = 300
        chunks_per_query = max(1, total_chunk_budget // total_queries)

        logger.info(
            f"Starting NEGATIVE news search for "
            f"{[c['ticker'] for c in companies]}: "
            f"{len(categories)} categories × {len(entity_batches)} entity batches "
            f"({chunks_per_query} chunks/query)"
        )

        tasks = []
        for batch in entity_batches:
            entity_ids = [c["entity_id"] for c in batch]
            entity_to_ticker = {c["entity_id"]: c["ticker"] for c in batch}
            for cat_idx, category in enumerate(categories):
                tasks.append(
                    self.search_negative_category(
                        entity_ids=entity_ids,
                        entity_to_ticker=entity_to_ticker,
                        category=category,
                        category_index=cat_idx,
                        days=days,
                        max_chunks=chunks_per_query,
                    )
                )

        all_articles: List[Dict] = []
        for i in range(0, len(tasks), batch_size):
            batch_tasks = tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            for result in batch_results:
                if isinstance(result, list):
                    all_articles.extend(result)
                elif isinstance(result, Exception):
                    logger.error(f"Negative category search failed: {result}")

        all_articles = self._deduplicate_across_topics(all_articles)
        if min_relevance > 0:
            all_articles = [
                r for r in all_articles if r.get("relevance", 0) >= min_relevance
            ]

        # Split results back per ticker
        by_ticker: Dict[str, List[Dict]] = {c["ticker"]: [] for c in companies}
        for article in all_articles:
            t = article.get("ticker")
            if t in by_ticker:
                by_ticker[t].append(article)
            elif companies:
                # Fallback if attribution missed
                by_ticker[companies[0]["ticker"]].append(article)

        elapsed = (datetime.now() - start_time).total_seconds()
        results = []
        for c in companies:
            ticker_articles = by_ticker.get(c["ticker"], [])
            results.append({
                "ticker": c["ticker"],
                "company_name": c["company_name"],
                "entity_id": c["entity_id"],
                "topic_results": ticker_articles,
                "total_results": len(ticker_articles),
                "search_stats": {
                    "categories_searched": len(categories),
                    "entity_batches": len(entity_batches),
                    "total_queries": total_queries,
                    "elapsed_seconds": round(elapsed, 2),
                    "rate_limiter_stats": self.rate_limiter.get_metrics(),
                },
            })
            logger.info(
                f"Completed negative search for {c['ticker']}: "
                f"{len(ticker_articles)} results in {elapsed:.2f}s"
            )

        return results

    async def search_ticker(
        self,
        ticker: str,
        days: int = 7,
        topics: Optional[List[str]] = None,
        batch_size: int = 50,
        custom_topics: Optional[List[str]] = None,
        min_relevance: float = 0.0,
        query_reformulation: bool = False
    ) -> Dict:
        """
        Search topics for a ticker (sentiment-filtered parallel topic searches).
        
        For baseline/entity-only search, use search_baseline() directly instead.
        
        Args:
            ticker: Stock ticker symbol
            days: Number of days to look back
            topics: List of topic templates (uses DEFAULT_TOPICS if None) - DEPRECATED
            batch_size: Number of concurrent requests per batch
            custom_topics: Custom list of topic templates (overrides topics parameter)
            min_relevance: Minimum relevance threshold to filter results
            query_reformulation: If True, use Gemini to generate 3 variations of each topic
            
        Returns:
            Dictionary with topic results and metadata
        """
        start_time = datetime.now()
        ticker = ticker.upper()
        
        mode_str = "TOPIC search with query reformulation" if query_reformulation else "TOPIC search"
        logger.info(f"Starting {mode_str} for {ticker}")
        
        # Get company data
        company_data = await self.get_company_data(ticker)
        if not company_data:
            logger.error(f"Could not resolve company data for {ticker}")
            return {
                "ticker": ticker,
                "error": "Company not found",
                "topic_results": [],
                "total_results": 0,
            }
        
        entity_id = company_data.entity_id
        company_name = company_data.company_name
        
        # Use custom_topics if provided, otherwise fallback to topics or DEFAULT_TOPICS
        base_topics = custom_topics or topics or DEFAULT_TOPICS
        
        # Generate topic variations if query reformulation is enabled
        search_topics_with_info = []  # List of (topic_text, is_variation, base_topic_index)
        
        if query_reformulation:
            logger.info(f"Generating query variations for {len(base_topics)} topics...")
            variation_start = datetime.now()
            
            # Generate variations for each topic in parallel
            variation_tasks = [
                self.generate_topic_variations(topic, company_name) 
                for topic in base_topics
            ]
            all_variations = await asyncio.gather(*variation_tasks, return_exceptions=True)
            
            # Build search topics list: original + variations
            for i, (base_topic, variations) in enumerate(zip(base_topics, all_variations)):
                # Extract topic_name from base topic (if it's a dict)
                if isinstance(base_topic, dict):
                    topic_name = base_topic.get("topic_name", f"Topic {i}")
                else:
                    topic_name = f"Topic {i}"
                
                # Add original topic
                search_topics_with_info.append((base_topic, False, i))
                
                # Add variations (if generation succeeded)
                # Wrap variations in dict with same topic_name as base topic
                if isinstance(variations, list) and variations:
                    for variation in variations:
                        # Create dict with same topic_name but variation text
                        variation_dict = {
                            "topic_name": topic_name,
                            "topic_text": variation
                        }
                        search_topics_with_info.append((variation_dict, True, i))
                elif isinstance(variations, Exception):
                    logger.warning(f"Failed to generate variations for topic {i}: {variations}")
            
            variation_elapsed = (datetime.now() - variation_start).total_seconds()
            logger.info(
                f"Generated variations in {variation_elapsed:.2f}s: "
                f"{len(base_topics)} original topics → {len(search_topics_with_info)} total queries"
            )
        else:
            # No reformulation: just use original topics
            search_topics_with_info = [(topic, False, i) for i, topic in enumerate(base_topics)]
        
        total_queries = len(search_topics_with_info)
        
        # Chunk budget divided across ALL queries (originals + variations)
        chunks_per_query = max(1, TOTAL_CHUNK_BUDGET // total_queries)  # Min 1 per query
        
        logger.info(
            f"Chunk allocation for {ticker}: "
            f"queries={total_queries} × {chunks_per_query} chunks "
            f"(total={chunks_per_query * total_queries}, budget={TOTAL_CHUNK_BUDGET})"
        )
        
        # Create all topic search tasks with metadata
        topic_tasks_with_info = [
            (
                self.search_single_topic(
                    ticker, entity_id, company_name, topic_text, query_idx, days,
                    max_chunks=chunks_per_query
                ),
                topic_text,
                is_variation,
                base_idx
            )
            for query_idx, (topic_text, is_variation, base_idx) in enumerate(search_topics_with_info)
        ]
        
        # Execute in batches to avoid overwhelming the system
        topic_results = []
        query_result_counts = []  # Track results per query for logging
        
        for i in range(0, len(topic_tasks_with_info), batch_size):
            batch = topic_tasks_with_info[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(topic_tasks_with_info) + batch_size - 1) // batch_size
            
            logger.info(
                f"Executing batch {batch_num}/{total_batches} "
                f"({len(batch)} searches) for {ticker}"
            )
            
            # Extract just the tasks for execution
            batch_tasks = [task for task, _, _, _ in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # Process results and log counts
            for (task, topic_text, is_variation, base_idx), result in zip(batch, batch_results):
                if isinstance(result, list):
                    result_count = len(result)
                    topic_results.extend(result)
                    
                    # Log query and result count
                    query_type = "Variation" if is_variation else "Original"
                    
                    # Handle both dict and string topic formats
                    if isinstance(topic_text, dict):
                        topic_str = topic_text.get("topic_text", str(topic_text))
                    else:
                        topic_str = topic_text
                    
                    # Format with company name if needed
                    formatted_topic = topic_str.format(company=company_name) if "{company}" in topic_str else topic_str
                    
                    # Truncate for log readability
                    truncated_query = formatted_topic[:70] + "..." if len(formatted_topic) > 70 else formatted_topic
                    logger.info(
                        f"  [{query_type}] {truncated_query} → {result_count} results"
                    )
                    
                    query_result_counts.append({
                        'query': formatted_topic,
                        'type': query_type,
                        'base_topic_idx': base_idx,
                        'count': result_count
                    })
                elif isinstance(result, Exception):
                    logger.error(f"Topic search failed: {result}")
        
        # Deduplicate across all topics (same article may appear in multiple topics/variations)
        raw_topic_count = len(topic_results)
        topic_results = self._deduplicate_across_topics(topic_results)
        
        if raw_topic_count > len(topic_results):
            logger.info(
                f"Cross-topic deduplication for {ticker}: "
                f"{raw_topic_count} raw -> {len(topic_results)} unique"
            )
        
        # Filter by relevance if needed
        if min_relevance > 0:
            topic_results = [r for r in topic_results if r.get("relevance", 0) >= min_relevance]
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Log query reformulation effectiveness summary
        if query_reformulation and query_result_counts:
            original_counts = [q['count'] for q in query_result_counts if q['type'] == 'Original']
            variation_counts = [q['count'] for q in query_result_counts if q['type'] == 'Variation']
            
            total_original = sum(original_counts)
            total_variations = sum(variation_counts)
            
            logger.info(
                f"Query Reformulation Summary for {ticker}:"
            )
            logger.info(
                f"  Original queries: {len(original_counts)} queries → {total_original} raw results"
            )
            logger.info(
                f"  Variation queries: {len(variation_counts)} queries → {total_variations} raw results"
            )
            logger.info(
                f"  Total raw results: {total_original + total_variations} → {len(topic_results)} after deduplication"
            )
            # Calculate percentage contribution, avoiding division by zero
            total_raw = total_original + total_variations
            if total_raw > 0:
                variation_pct = (total_variations / total_raw) * 100
                logger.info(
                    f"  Variations contributed: {total_variations} additional results ({variation_pct:.1f}% of raw results)"
                )
            else:
                logger.info(
                    f"  Variations contributed: {total_variations} additional results (0% of raw results - no results found)"
                )
        
        logger.info(
            f"Completed topic search for {ticker}: "
            f"{len(topic_results)} results in {elapsed:.2f}s"
        )
        
        return {
            "ticker": ticker,
            "company_name": company_name,
            "entity_id": entity_id,
            "topic_results": topic_results,
            "total_results": len(topic_results),
            "search_stats": {
                "topics_searched": len(base_topics),
                "total_queries": total_queries,
                "query_reformulation_enabled": query_reformulation,
                "elapsed_seconds": round(elapsed, 2),
                "rate_limiter_stats": self.rate_limiter.get_metrics(),
            }
        }
    
    async def search_multiple_tickers(
        self,
        tickers: List[str],
        days: int = 7,
        topics: Optional[List[str]] = None,
        custom_topics: Optional[List[str]] = None,
        min_relevance: float = 0.0,
        query_reformulation: bool = False
    ) -> List[Dict]:
        """
        Search multiple tickers in parallel (topic searches only).
        
        For baseline searches, call search_baseline() for each ticker instead.
        
        Args:
            tickers: List of stock ticker symbols
            days: Number of days to look back
            topics: List of topic templates (uses DEFAULT_TOPICS if None) - DEPRECATED
            custom_topics: Custom list of topic templates (overrides topics parameter)
            min_relevance: Minimum relevance threshold to filter results
            query_reformulation: If True, use Gemini to generate 3 variations of each topic
            
        Returns:
            List of results dictionaries, one per ticker
        """
        mode_str = "with query reformulation" if query_reformulation else "standard"
        logger.info(f"Searching {len(tickers)} tickers (TOPIC mode, {mode_str}): {', '.join(tickers)}")
        
        tasks = [
            self.search_ticker(
                ticker, 
                days, 
                topics=topics,
                custom_topics=custom_topics,
                min_relevance=min_relevance,
                query_reformulation=query_reformulation
            )
            for ticker in tickers
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, dict):
                valid_results.append(result)
            else:
                logger.error(f"Failed to search ticker {tickers[i]}: {result}")
                valid_results.append({
                    "ticker": tickers[i],
                    "error": str(result),
                    "topic_results": [],
                    "total_results": 0,
                })
        
        return valid_results
    
    async def _expand_sector_topics(
        self,
        topics: List[Dict],
        expansion_prompt: str
    ) -> List[Dict]:
        """
        Expand each theme phrase into itself plus up to 3 AI-generated variations.
        
        Variations inherit the parent's ``topic_name`` so they collapse into the same
        UI topic tab, and are flagged with ``is_variation`` for the search stats.
        
        Args:
            topics: Original theme topics
            expansion_prompt: Sector-specific expansion guidance
            
        Returns:
            Combined list of original and variation topics
        """
        variation_start = datetime.now()
        logger.info(f"Generating query variations for {len(topics)} theme phrases...")
        
        all_variations = await asyncio.gather(
            *(self.generate_theme_variations(topic, expansion_prompt) for topic in topics),
            return_exceptions=True
        )
        
        expanded: List[Dict] = []
        for i, (topic, variations) in enumerate(zip(topics, all_variations)):
            topic_name = topic.get("topic_name") or f"Topic {i + 1}"
            expanded.append({**topic, "is_variation": False})
            
            if isinstance(variations, list):
                expanded.extend(
                    {"topic_name": topic_name, "topic_text": variation, "is_variation": True}
                    for variation in variations
                )
            else:
                logger.warning(f"Failed to expand theme phrase {i}: {variations}")
        
        elapsed = (datetime.now() - variation_start).total_seconds()
        logger.info(
            f"Generated theme variations in {elapsed:.2f}s: "
            f"{len(topics)} original phrases -> {len(expanded)} total queries"
        )
        return expanded
    
    async def search_sector(
        self,
        sector_id: str,
        topics: List[Dict],
        days: float = 7,
        min_relevance: float = 0.0,
        batch_size: int = 50,
        sector_label: Optional[str] = None,
        query_reformulation: bool = False,
        expansion_prompt: str = ""
    ) -> Dict:
        """
        Search a sector's theme topics in parallel (no entity resolution).
        
        Args:
            sector_id: Sector identifier used to tag results
            topics: Topic dicts with {topic_name, topic_text} and no {company} placeholder
            days: Number of days to look back
            min_relevance: Minimum relevance threshold to filter results
            batch_size: Number of concurrent requests per batch
            sector_label: Display label echoed back to the caller
            query_reformulation: If True, use Gemini to add 3 variations per phrase
            expansion_prompt: Sector-specific expansion guidance (required when expanding)
            
        Returns:
            Dictionary with theme results and metadata
        """
        start_time = datetime.now()
        mode = "SECTOR search with query expansion" if query_reformulation else "SECTOR search"
        logger.info(f"Starting {mode} for {sector_id} ({len(topics)} topics, {days} days)")
        
        if not topics:
            return {
                "sector": sector_id,
                "sector_label": sector_label or sector_id,
                "theme_results": [],
                "total_results": 0,
                "search_stats": {
                    "topics_searched": 0,
                    "queries_executed": 0,
                    "variations_generated": 0,
                    "query_reformulation": query_reformulation,
                    "elapsed_seconds": 0.0,
                    "rate_limiter_stats": self.rate_limiter.get_metrics(),
                },
            }
        
        if query_reformulation:
            search_topics = await self._expand_sector_topics(topics, expansion_prompt)
        else:
            search_topics = [{**topic, "is_variation": False} for topic in topics]
        
        variations_generated = sum(1 for t in search_topics if t["is_variation"])
        
        # Chunk budget divided across ALL queries (originals + variations)
        chunks_per_query = max(1, TOTAL_CHUNK_BUDGET // len(search_topics))
        logger.info(
            f"Chunk allocation for {sector_id}: "
            f"queries={len(search_topics)} x {chunks_per_query} chunks (budget={TOTAL_CHUNK_BUDGET})"
        )
        
        theme_results: List[Dict] = []
        
        for offset in range(0, len(search_topics), batch_size):
            batch = search_topics[offset:offset + batch_size]
            batch_tasks = [
                self.search_single_theme(
                    topic,
                    offset + i,
                    days=days,
                    max_chunks=chunks_per_query,
                    sector=sector_id,
                )
                for i, topic in enumerate(batch)
            ]
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for topic, result in zip(batch, batch_results):
                if isinstance(result, list):
                    theme_results.extend(result)
                    topic_text = topic.get("topic_text", "")
                    truncated = topic_text[:70] + "..." if len(topic_text) > 70 else topic_text
                    label = "Variation" if topic["is_variation"] else "Theme"
                    logger.info(f"  [{label}] {truncated} -> {len(result)} results")
                else:
                    logger.error(f"Theme search failed: {result}")
        
        # Same article can surface under several themes (and variations of one theme
        # overlap heavily by design) - keep the highest relevance copy
        raw_count = len(theme_results)
        theme_results = self._deduplicate_across_topics(theme_results)
        if raw_count > len(theme_results):
            logger.info(
                f"Cross-theme deduplication for {sector_id}: "
                f"{raw_count} raw -> {len(theme_results)} unique"
            )
        
        if min_relevance > 0:
            theme_results = [r for r in theme_results if r.get("relevance", 0) >= min_relevance]
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"Completed sector search for {sector_id}: "
            f"{len(theme_results)} results in {elapsed:.2f}s"
        )
        
        return {
            "sector": sector_id,
            "sector_label": sector_label or sector_id,
            "theme_results": theme_results,
            "total_results": len(theme_results),
            "search_stats": {
                "topics_searched": len(topics),
                "queries_executed": len(search_topics),
                "variations_generated": variations_generated,
                "query_reformulation": query_reformulation,
                "chunks_per_query": chunks_per_query,
                "elapsed_seconds": round(elapsed, 2),
                "rate_limiter_stats": self.rate_limiter.get_metrics(),
            },
        }


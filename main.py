#!/usr/bin/env python3
"""
Financial News Terminal
Single-file FastAPI backend with Bigdata.com API integration
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import requests
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
import uvicorn
from dotenv import load_dotenv
import logging
from contextlib import asynccontextmanager

# Import services
from services import price_service
from services.topic_search_service import TopicSearchService
from services.report_service import ReportService
from config.topics import DEFAULT_TOPICS, list_available_configs


# Pydantic models for request bodies
class TopicItem(BaseModel):
    """A single topic with name and text template"""
    topic_name: str
    topic_text: str


class NewsSearchRequest(BaseModel):
    """Request body for news search endpoint"""
    days: int = Field(default=7, description="Number of days to look back")
    basic_search: bool = Field(default=False, description="If true, use basic search without topics")
    relevance: float = Field(default=0.1, description="Minimum relevance threshold (0.0-1.0)")
    topics: Optional[List[TopicItem]] = Field(default=None, description="Custom topics for search")
    since_minutes: Optional[int] = Field(default=None, description="For incremental refresh: only fetch last N minutes")
    query_reformulation: bool = Field(default=False, description="Enable AI query expansion")


class NewsMultiSearchRequest(BaseModel):
    """Request body for multi-ticker news search endpoint"""
    tickers: List[str] = Field(..., description="List of ticker symbols")
    days: int = Field(default=7, description="Number of days to look back")
    basic_search: bool = Field(default=False, description="If true, use basic search without topics")
    relevance: float = Field(default=0.1, description="Minimum relevance threshold (0.0-1.0)")
    topics: Optional[List[TopicItem]] = Field(default=None, description="Custom topics for search")
    since_minutes: Optional[int] = Field(default=None, description="For incremental refresh: only fetch last N minutes")
    query_reformulation: bool = Field(default=False, description="Enable AI query expansion")

# Load environment variables
load_dotenv()

# Configure logging (allow override via environment variable)
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Ensure service loggers also show up
service_logger = logging.getLogger('services.topic_search_service')
service_logger.setLevel(getattr(logging, log_level, logging.INFO))

logger.info(f"Logging configured at {log_level} level")

# Global service instances
topic_search_service: Optional[TopicSearchService] = None
report_service: Optional[ReportService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service lifecycle (startup/shutdown)"""
    global topic_search_service, report_service
    
    # Startup: Initialize services
    logger.info("Starting up: Initializing services...")
    topic_search_service = TopicSearchService(
        api_key=BIGDATA_API_KEY,
        base_url=BIGDATA_BASE_URL
    )
    logger.info("TopicSearchService initialized")
    
    # Initialize ReportService (for commentary generation)
    try:
        report_service = ReportService()
        logger.info("ReportService initialized")
    except Exception as e:
        logger.warning(f"ReportService initialization failed: {e}. Commentary features will be unavailable.")
        report_service = None
    
    yield
    
    # Shutdown: Close HTTP session
    logger.info("Shutting down: Closing services...")
    if topic_search_service:
        await topic_search_service.close()
    logger.info("Services closed")


# FastAPI app with lifespan management
app = FastAPI(
    title="News Terminal MVP",
    description="Financial news terminal with topic-based search",
    version="2.0.0",
    lifespan=lifespan
)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configuration
BIGDATA_API_KEY = os.getenv("BIGDATA_API_KEY")
BIGDATA_BASE_URL = "https://api.bigdata.com/v1"

if not BIGDATA_API_KEY:
    logger.error("BIGDATA_API_KEY not found in environment variables")
    raise ValueError("BIGDATA_API_KEY environment variable is required")

# Simple in-memory caches
news_cache: Dict[str, Dict] = {}
entity_cache: Dict[str, str] = {}  # ticker -> entity_id
CACHE_TTL_MINUTES = 5

def is_cache_valid(timestamp: datetime) -> bool:
    """Check if cache entry is still valid"""
    return datetime.now() - timestamp < timedelta(minutes=CACHE_TTL_MINUTES)

def format_timestamp(dt: datetime) -> str:
    """Format datetime to ISO 8601 with milliseconds and Z suffix"""
    # Ensure datetime is UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    
    # Format with milliseconds (3 decimal places)
    iso_str = dt.strftime('%Y-%m-%dT%H:%M:%S')
    milliseconds = dt.microsecond // 1000
    return f"{iso_str}.{milliseconds:03d}Z"

def get_entity_id(ticker: str) -> Optional[str]:
    """Get entity ID for ticker with caching"""
    
    if ticker in entity_cache:
        logger.info(f"Cache hit for entity ID: {ticker}")
        return entity_cache[ticker]
    
    logger.info(f"Fetching entity ID for ticker: {ticker}")
    
    try:
        response = requests.post(
            f"{BIGDATA_BASE_URL}/knowledge-graph/companies",
            headers={
                "X-API-KEY": BIGDATA_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "query": ticker,
                "types": ["PUBLIC"]
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            companies = data.get("results", [])
            if companies:
                entity_id = companies[0]["id"]
                company_name = companies[0]["name"]
                entity_cache[ticker] = entity_id
                logger.info(f"Found entity: {company_name} ({ticker}) -> {entity_id}")
                return entity_id
            else:
                logger.warning(f"No companies found for ticker: {ticker}")
        else:
            logger.error(f"Knowledge Graph API error: {response.status_code} - {response.text}")
            
    except requests.RequestException as e:
        logger.error(f"Request error getting entity ID for {ticker}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting entity ID for {ticker}: {str(e)}")
    
    return None

def get_ticker_news(ticker: str, days: int = 7) -> List[Dict]:
    """Get news for ticker with simple caching"""
    
    cache_key = f"{ticker}_{days}"
    
    # Check cache
    if cache_key in news_cache:
        cached_data = news_cache[cache_key]
        if is_cache_valid(cached_data["timestamp"]):
            logger.info(f"Cache hit for news: {ticker}")
            return cached_data["news"]
    
    logger.info(f"Fetching news for ticker: {ticker} (last {days} days)")
    
    # Get entity ID
    entity_id = get_entity_id(ticker)
    if not entity_id:
        logger.warning(f"Could not resolve entity ID for {ticker}")
        return []
    
    # Search news using entity ID
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    try:
        response = requests.post(
            f"{BIGDATA_BASE_URL}/search",
            headers={
                "X-API-KEY": BIGDATA_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "query": {
                    "text": "earnings financial results stock news",
                    "filters": {
                        "timestamp": {
                            "start": format_timestamp(start_time),
                            "end": format_timestamp(end_time)
                        },
                        "entity": {
                            "all_of": [entity_id]
                        },
                        "document_type": {
                            "mode": "INCLUDE",
                            "values": ["NEWS", "TRANSCRIPT"]
                        }
                    },
                    "max_chunks": 100
                },
                "rerank_threshold": 0.1
            },
            timeout=30
        )
        
        news = []
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            
            logger.info(f"Found {len(results)} articles for {ticker}")
            
            for i, article in enumerate(results):
                # Get the best content chunk
                chunks = article.get("chunks", [])
                best_chunk = ""
                full_text = ""
                if chunks:
                    # Sort by relevance and take the best one
                    sorted_chunks = sorted(chunks, key=lambda x: x.get("relevance", 0), reverse=True)
                    full_text = sorted_chunks[0].get("text", "")
                    best_chunk = full_text
                
                # Create summary (first 200 chars) for preview
                summary = best_chunk[:200] + "..." if len(best_chunk) > 200 else best_chunk
                
                # Parse timestamp
                timestamp = article.get("timestamp", "")
                try:
                    parsed_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_ago = get_time_ago(parsed_time)
                except:
                    time_ago = "Unknown time"
                
                news_item = {
                    "id": article.get("id", f"article_{i}"),
                    "headline": article.get("headline", "No headline"),
                    "timestamp": timestamp,
                    "time_ago": time_ago,
                    "source": article.get("source", {}).get("name", "Unknown"),
                    "summary": summary,
                    "full_text": full_text,  # Full chunk text for expanded view
                    "document_url": article.get("url"),  # URL to original article (from "url" field)
                    "relevance": chunks[0].get("relevance", 0) if chunks else 0,
                    "document_type": article.get("document_type", "NEWS")
                }
                news.append(news_item)
            
            # Sort by relevance and recency
            news.sort(key=lambda x: (x["relevance"], x["timestamp"]), reverse=True)
            
        else:
            logger.error(f"Search API error: {response.status_code} - {response.text}")
            
    except requests.RequestException as e:
        logger.error(f"Request error getting news for {ticker}: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error getting news for {ticker}: {str(e)}")
        return []
    
    # Cache result
    news_cache[cache_key] = {
        "news": news,
        "timestamp": datetime.now()
    }
    
    return news

def get_time_ago(timestamp: datetime) -> str:
    """Convert timestamp to human-readable time ago"""
    now = datetime.now(timestamp.tzinfo) if timestamp.tzinfo else datetime.now()
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

# API Routes

@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the terminal interface"""
    try:
        with open("static/index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="""
            <html>
                <body>
                    <h1>News Terminal</h1>
                    <p>Frontend not yet deployed. Please create static/index.html</p>
                    <p>API is running at <a href="/docs">/docs</a></p>
                </body>
            </html>
            """,
            status_code=200
        )

@app.post("/api/news/{ticker}")
async def get_news(
    ticker: str,
    request: NewsSearchRequest
):
    """
    Get news for a ticker (POST request with JSON body).
    
    Two modes:
    - basic_search=true: Entity-filtered baseline search (no topics, no sentiment filter)
    - basic_search=false: Topic-based search with sentiment filtering (default)
    
    Request body parameters:
    - days: Number of days to look back (default: 7)
    - basic_search: If true, only run baseline search (no topics); if false, run topic searches
    - relevance: Minimum relevance threshold (0.0-1.0)
    - topics: Array of topic objects with topic_name and topic_text (only for topic search)
    - since_minutes: If provided, only fetch articles from the last N minutes (incremental refresh)
    - query_reformulation: If true, generate 3 variations for each topic using Gemini AI (4x searches)
    """
    
    # Extract values from request body
    days = request.days
    basic_search = request.basic_search
    relevance = request.relevance
    topics = request.topics
    since_minutes = request.since_minutes
    query_reformulation = request.query_reformulation
    
    # Validate ticker
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")
    
    if not topic_search_service:
        raise HTTPException(status_code=503, detail="Search service not initialized")
    
    try:
        # Determine lookback period (use since_minutes for incremental refresh)
        if since_minutes:
            # Convert minutes to fractional days for incremental refresh
            lookback_days = since_minutes / (60 * 24)
            # Add 1 minute buffer to avoid missing articles on boundary
            lookback_days = max(lookback_days, 1 / (60 * 24))  # Minimum 1 minute
            logger.info(f"API request for news: {ticker} (INCREMENTAL: last {since_minutes} minutes, basic={basic_search})")
        else:
            # Regular full fetch
            lookback_days = days
            logger.info(f"API request for news: {ticker} (FULL: {days} days, basic={basic_search})")
        
        # Handle basic_search vs topic_search separately
        if basic_search:
            # Basic search: call search_baseline directly
            company_data = await topic_search_service.get_company_data(ticker)
            if not company_data:
                raise HTTPException(status_code=404, detail="Company not found")
            
            baseline_results = await topic_search_service.search_baseline(
                ticker,
                company_data.entity_id,
                days=lookback_days,
                max_chunks=100
            )
            
            # Filter by relevance
            if relevance > 0:
                baseline_results = [r for r in baseline_results if r.get("relevance", 0) >= relevance]
            
            return {
                "ticker": ticker,
                "company_name": company_data.company_name,
                "entity_id": company_data.entity_id,
                "baseline_results": baseline_results,
                "topic_results": [],
                "total_results": len(baseline_results),
                "counts": {
                    "baseline": len(baseline_results),
                    "topics": 0,
                    "total": len(baseline_results)
                },
                "search_stats": {
                    "topics_searched": 0,
                    "rate_limiter_stats": topic_search_service.rate_limiter.get_metrics(),
                },
                "settings": {
                    "basic_search": basic_search,
                    "days": days,
                    "relevance": relevance
                },
                "timestamp": datetime.now().isoformat()
            }
        else:
            # Topic search: call search_ticker
            # Convert Pydantic TopicItem objects to dicts for the service
            custom_topics = None
            if topics:
                custom_topics = [{"topic_name": t.topic_name, "topic_text": t.topic_text} for t in topics]
                logger.info(f"Using {len(custom_topics)} custom topics")
            
            results = await topic_search_service.search_ticker(
                ticker, 
                lookback_days,
                custom_topics=custom_topics,
                min_relevance=relevance,
                query_reformulation=query_reformulation
            )
            
            # Check for errors
            if "error" in results:
                raise HTTPException(status_code=404, detail=results["error"])
            
            return {
                "ticker": results["ticker"],
                "company_name": results.get("company_name"),
                "entity_id": results.get("entity_id"),
                "baseline_results": [],
                "topic_results": results["topic_results"],
                "total_results": results["total_results"],
                "counts": {
                    "baseline": 0,
                    "topics": len(results["topic_results"]),
                    "total": results["total_results"]
                },
                "search_stats": results.get("search_stats", {}),
                "settings": {
                    "basic_search": basic_search,
                    "days": days,
                    "relevance": relevance
                },
                "timestamp": datetime.now().isoformat()
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing request for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/api/news-multi")
async def get_news_multi(request: NewsMultiSearchRequest):
    """
    Get news for multiple tickers (POST request with JSON body).
    
    Two modes:
    - basic_search=true: Entity-filtered baseline search for each ticker (no topics)
    - basic_search=false: Topic-based search for each ticker (default)
    
    Request body parameters:
    - tickers: Array of ticker symbols
    - days: Number of days to look back (default: 7)
    - basic_search: If true, only run baseline searches; if false, run topic searches
    - relevance: Minimum relevance threshold (0.0-1.0)
    - topics: Array of topic objects with topic_name and topic_text
    - since_minutes: If provided, only fetch articles from the last N minutes (incremental refresh)
    - query_reformulation: If true, generate 3 variations for each topic using Gemini AI (4x searches)
    """
    
    # Extract values from request body
    days = request.days
    basic_search = request.basic_search
    relevance = request.relevance
    topics = request.topics
    since_minutes = request.since_minutes
    query_reformulation = request.query_reformulation
    
    # Parse and validate tickers
    ticker_list = [t.upper().strip() for t in request.tickers if t.strip()]
    
    if not ticker_list:
        raise HTTPException(status_code=400, detail="No valid tickers provided")
    
    if len(ticker_list) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 tickers allowed (topic search is intensive)")
    
    if not topic_search_service:
        raise HTTPException(status_code=503, detail="Search service not initialized")
    
    try:
        # Determine lookback period (use since_minutes for incremental refresh)
        if since_minutes:
            # Convert minutes to fractional days for incremental refresh
            lookback_days = since_minutes / (60 * 24)
            # Add 1 minute buffer to avoid missing articles on boundary
            lookback_days = max(lookback_days, 1 / (60 * 24))  # Minimum 1 minute
            logger.info(f"API request for multiple tickers: {', '.join(ticker_list)} (INCREMENTAL: last {since_minutes} minutes, basic={basic_search})")
        else:
            # Regular full fetch
            lookback_days = days
            logger.info(f"API request for multiple tickers: {', '.join(ticker_list)} (FULL: {days} days, basic={basic_search})")
        
        # Handle basic_search vs topic_search separately
        if basic_search:
            # Basic search: call search_baseline for each ticker
            results_list = []
            for ticker in ticker_list:
                try:
                    company_data = await topic_search_service.get_company_data(ticker)
                    if not company_data:
                        results_list.append({
                            "ticker": ticker,
                            "error": "Company not found",
                            "baseline_results": [],
                            "topic_results": [],
                            "total_results": 0,
                        })
                        continue
                    
                    baseline_results = await topic_search_service.search_baseline(
                        ticker,
                        company_data.entity_id,
                        days=lookback_days,
                        max_chunks=100
                    )
                    
                    # Filter by relevance
                    if relevance > 0:
                        baseline_results = [r for r in baseline_results if r.get("relevance", 0) >= relevance]
                    
                    results_list.append({
                        "ticker": ticker,
                        "company_name": company_data.company_name,
                        "entity_id": company_data.entity_id,
                        "baseline_results": baseline_results,
                        "topic_results": [],
                        "total_results": len(baseline_results),
                    })
                except Exception as e:
                    logger.error(f"Error searching {ticker}: {e}")
                    results_list.append({
                        "ticker": ticker,
                        "error": str(e),
                        "baseline_results": [],
                        "topic_results": [],
                        "total_results": 0,
                    })
        else:
            # Topic search: call search_multiple_tickers
            # Convert Pydantic TopicItem objects to dicts for the service
            custom_topics = None
            if topics:
                custom_topics = [{"topic_name": t.topic_name, "topic_text": t.topic_text} for t in topics]
                logger.info(f"Using {len(custom_topics)} custom topics")
            
            results_list = await topic_search_service.search_multiple_tickers(
                ticker_list, 
                lookback_days,
                custom_topics=custom_topics,
                min_relevance=relevance,
                query_reformulation=query_reformulation
            )
            
            # Add baseline_results field (empty) for consistency
            for result in results_list:
                result["baseline_results"] = []
        
        # Calculate aggregate statistics
        total_baseline = sum(len(r.get("baseline_results", [])) for r in results_list)
        total_topics = sum(len(r.get("topic_results", [])) for r in results_list)
        total_results = sum(r.get("total_results", 0) for r in results_list)
        
        ticker_stats = {
            r["ticker"]: {
                "baseline": len(r.get("baseline_results", [])),
                "topics": len(r.get("topic_results", [])),
                "total": r.get("total_results", 0),
                "company_name": r.get("company_name"),
                "error": r.get("error")
            }
            for r in results_list
        }
        
        # Get aggregate rate limiter stats
        rate_stats = topic_search_service.rate_limiter.get_metrics() if results_list else {}
        
        return {
            "tickers": ticker_list,
            "results": results_list,
            "aggregate_stats": {
                "total_baseline": total_baseline,
                "total_topics": total_topics,
                "total_results": total_results,
                "ticker_count": len(ticker_list)
            },
            "ticker_stats": ticker_stats,
            "rate_limiter_stats": rate_stats,
            "settings": {
                "basic_search": basic_search,
                "days": days,
                "relevance": relevance
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing multi-ticker request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/api/search/{query}")
async def search_news(query: str, days: int = 7):
    """Search news by text query (fallback for when entity lookup fails)"""
    
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty")
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    try:
        response = requests.post(
            f"{BIGDATA_BASE_URL}/search",
            headers={
                "X-API-KEY": BIGDATA_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "query": {
                    "text": query,
                    "filters": {
                        "timestamp": {
                            "start": format_timestamp(start_time),
                            "end": format_timestamp(end_time)
                        },
                        "document_type": {
                            "mode": "INCLUDE",
                            "values": ["NEWS", "TRANSCRIPT"]
                        }
                    },
                    "max_chunks": 10
                }
            },
            timeout=30
        )
        
        news = []
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            
            for i, article in enumerate(results):
                chunks = article.get("chunks", [])
                summary = chunks[0].get("text", "")[:200] + "..." if chunks else ""
                
                news_item = {
                    "id": article.get("id", f"search_{i}"),
                    "headline": article.get("headline", "No headline"),
                    "timestamp": article.get("timestamp", ""),
                    "source": article.get("source", {}).get("name", "Unknown"),
                    "summary": summary,
                    "relevance": chunks[0].get("relevance", 0) if chunks else 0
                }
                news.append(news_item)
        
        return {
            "query": query,
            "news": news,
            "count": len(news),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error searching for '{query}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/prices")
async def get_prices(tickers: str):
    """
    Get price data for comma-separated tickers
    Returns: {"AAPL": {"price": 175.50, "change": 2.34, "currency": "USD"}, ...}
    """
    try:
        # Parse tickers
        ticker_list = [t.strip().upper() for t in tickers.split(',')]
        
        if not ticker_list:
            raise HTTPException(status_code=400, detail="No tickers provided")
        
        if len(ticker_list) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 tickers allowed")
        
        logger.info(f"Fetching prices for: {', '.join(ticker_list)}")
        
        # Get entity IDs for all tickers (reuse from news cache)
        tickers_with_entities = []
        for ticker in ticker_list:
            entity_id = get_entity_id(ticker)
            if entity_id:
                tickers_with_entities.append((ticker, entity_id))
            else:
                logger.warning(f"Could not find entity ID for {ticker}")
        
        if not tickers_with_entities:
            raise HTTPException(status_code=404, detail="No valid tickers found")
        
        # Fetch prices using price service
        price_data = price_service.get_prices_for_tickers(tickers_with_entities)
        
        # Format response
        response = {}
        for ticker, data in price_data.items():
            response[ticker] = {
                "price": data.get("price"),
                "change": data.get("change"),
                "currency": data.get("currency", "USD")
            }
        
        return {
            "prices": response,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching prices: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/api/generate-commentary")
async def generate_commentary(news_data: Dict):
    """
    Generate AI-powered commentary (briefs + desk note) from news data.
    
    This endpoint takes the already-fetched news response and generates:
    - Executive briefs (one bullet point per topic)
    - Wall Street-style desk note (cohesive narrative)
    
    Parameters:
    - news_data: The complete response from /api/news endpoint
                 Should contain: ticker, company_name, topic_results
    
    Returns:
    - ticker: Stock ticker
    - company_name: Company name
    - generated_at: ISO timestamp
    - briefs: Array of {company_name, topic_name, bullet_point}
    - desk_note: Wall Street-style narrative text
    """
    
    if not report_service:
        raise HTTPException(
            status_code=503,
            detail="Commentary service not available. Check Gemini API configuration."
        )
    
    # Validate required fields
    if 'topic_results' not in news_data:
        raise HTTPException(
            status_code=400,
            detail="Invalid news_data: 'topic_results' field is required"
        )
    
    ticker = news_data.get('ticker', 'UNKNOWN')
    logger.info(f"Generating commentary for {ticker}")
    
    try:
        # Generate commentary using report service
        commentary = await report_service.generate_commentary(news_data)
        
        # Convert to dict for JSON response
        return {
            "ticker": commentary.ticker,
            "company_name": commentary.company_name,
            "generated_at": commentary.generated_at,
            "briefs": [
                {
                    "company_name": brief.company_name,
                    "topic_name": brief.topic_name,
                    "bullet_point": brief.bullet_point
                }
                for brief in commentary.briefs
            ],
            "desk_note": commentary.desk_note
        }
        
    except Exception as e:
        logger.error(f"Error generating commentary for {ticker}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate commentary: {str(e)}"
        )

@app.get("/api/config")
async def get_config():
    """Get default configuration including topics"""
    return {
        "default_topics": DEFAULT_TOPICS,
        "available_configs": list_available_configs(),
        "topic_count": len(DEFAULT_TOPICS),
        "commentary_available": report_service is not None
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "cache_stats": {
            "entity_cache_size": len(entity_cache),
            "news_cache_size": len(news_cache),
            "price_cache_size": len(price_service.price_cache)
        },
        "api_key_configured": bool(BIGDATA_API_KEY)
    }

@app.post("/api/cache/clear")
async def clear_cache():
    """Clear all caches"""
    global news_cache, entity_cache
    
    old_news_size = len(news_cache)
    old_entity_size = len(entity_cache)
    old_price_size = len(price_service.price_cache)
    
    news_cache.clear()
    entity_cache.clear()
    price_service.clear_cache()
    
    logger.info("All caches cleared")
    
    return {
        "message": "Caches cleared",
        "cleared": {
            "news_cache": old_news_size,
            "entity_cache": old_entity_size,
            "price_cache": old_price_size
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/cache/stats")
async def cache_stats():
    """Get cache statistics"""
    return {
        "cache_stats": {
            "entity_cache": {
                "size": len(entity_cache),
                "entries": list(entity_cache.keys())
            },
            "news_cache": {
                "size": len(news_cache),
                "entries": [
                    {
                        "key": key,
                        "timestamp": str(data["timestamp"]),
                        "article_count": len(data["news"]),
                        "valid": is_cache_valid(data["timestamp"])
                    }
                    for key, data in news_cache.items()
                ]
            }
        },
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    logger.info("Starting News Terminal MVP...")
    logger.info(f"API Key configured: {bool(BIGDATA_API_KEY)}")
    
    # Configure uvicorn to use our logging
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["default"]["fmt"] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_config["formatters"]["access"]["fmt"] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        log_config=log_config
    )

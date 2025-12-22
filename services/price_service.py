"""
Price Service for News Terminal
Handles fetching and caching of stock prices and price changes from Bigdata API
"""

import os
import requests
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Tuple

logger = logging.getLogger(__name__)

# Configuration
BIGDATA_API_KEY = os.getenv("BIGDATA_API_KEY")
BIGDATA_BASE_URL = "https://api.bigdata.com/v1"
CACHE_TTL_MINUTES = 15  # 15 minute cache

# Price cache: {ticker: {price, change, currency, timestamp}}
price_cache: Dict[str, Dict] = {}


def format_timestamp(dt: datetime) -> str:
    """Format datetime to ISO 8601 with milliseconds and Z suffix"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    
    iso_str = dt.strftime('%Y-%m-%dT%H:%M:%S')
    milliseconds = dt.microsecond // 1000
    return f"{iso_str}.{milliseconds:03d}Z"


def is_cache_valid(cache_entry: Dict) -> bool:
    """Check if cache entry is still valid (within TTL)"""
    if "timestamp" not in cache_entry:
        return False
    
    age = datetime.now(timezone.utc) - cache_entry["timestamp"]
    return age < timedelta(minutes=CACHE_TTL_MINUTES)


def get_latest_price(entity_id: str, ticker: str) -> Optional[Dict]:
    """
    Fetch the latest intraday price for a ticker
    Returns: {"price": float, "currency": str} or None
    """
    try:
        # Use last trading day's data (today or previous day if market closed)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=2)  # Look back 2 days to ensure we get data
        
        response = requests.post(
            f"{BIGDATA_BASE_URL}/price/intraday/query",
            headers={
                "X-API-KEY": BIGDATA_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "identifier": {
                    "type": "rp_entity_id",
                    "value": entity_id
                },
                "timestamp": {
                    "start": format_timestamp(start_time),
                    "end": format_timestamp(end_time)
                },
                "interval": "1hour"  # Use hourly data to get most recent
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", {})
            
            # Check if we have values
            if results and "values" in results and results["values"]:
                values = results["values"]
                fields = results.get("fields", [])
                
                # Find indices for the fields we need
                try:
                    close_idx = fields.index("CLOSE")
                    currency_idx = fields.index("CURRENCY")
                    
                    # Values can be either:
                    # 1. A single array: [timestamp, open, low, high, close, volume, currency]
                    # 2. Multiple arrays: [[...], [...], ...]
                    if isinstance(values[0], list):
                        # Multiple data points - get the last (most recent) one
                        latest_values = values[-1]
                        close_price = latest_values[close_idx]
                        currency = latest_values[currency_idx]
                    else:
                        # Single data point
                        close_price = values[close_idx]
                        currency = values[currency_idx]
                    
                    logger.info(f"Latest price for {ticker}: {close_price} {currency}")
                    return {
                        "price": close_price,
                        "currency": currency
                    }
                except (ValueError, IndexError) as e:
                    logger.error(f"Error parsing price data for {ticker}: {e}")
                    return None
            else:
                logger.warning(f"No price data available for {ticker}")
                return None
        else:
            logger.error(f"Price API error for {ticker}: {response.status_code} - {response.text}")
            return None
            
    except requests.RequestException as e:
        logger.error(f"Request error fetching price for {ticker}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching price for {ticker}: {e}")
        return None


def get_price_change(entity_id: str, ticker: str) -> Optional[float]:
    """
    Fetch the 1D price change percentage for a ticker
    Returns: float (percentage change) or None
    """
    try:
        response = requests.post(
            f"{BIGDATA_BASE_URL}/price/changes/query",
            headers={
                "X-API-KEY": BIGDATA_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "identifier": {
                    "type": "rp_entity_id",
                    "value": entity_id
                }
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            
            if results and len(results) > 0:
                change_1d = results[0].get("1D")
                logger.info(f"Price change for {ticker}: {change_1d}%")
                return change_1d
            else:
                logger.warning(f"No price change data for {ticker}")
                return None
        else:
            logger.error(f"Price change API error for {ticker}: {response.status_code}")
            return None
            
    except requests.RequestException as e:
        logger.error(f"Request error fetching price change for {ticker}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching price change for {ticker}: {e}")
        return None


def get_price_data(entity_id: str, ticker: str) -> Dict:
    """
    Get complete price data (price + change) for a ticker with caching
    Returns: {"price": float, "change": float, "currency": str}
    """
    # Check cache first
    if ticker in price_cache and is_cache_valid(price_cache[ticker]):
        logger.info(f"Price cache hit for {ticker}")
        return price_cache[ticker]
    
    logger.info(f"Fetching price data for {ticker}")
    
    # Fetch price and change
    price_data = get_latest_price(entity_id, ticker)
    change_data = get_price_change(entity_id, ticker)
    
    # Build result
    result = {
        "price": price_data.get("price") if price_data else None,
        "change": change_data,
        "currency": price_data.get("currency", "USD") if price_data else "USD",
        "timestamp": datetime.now(timezone.utc)
    }
    
    # Cache the result
    price_cache[ticker] = result
    
    return result


def get_prices_for_tickers(tickers_with_entities: List[Tuple[str, str]]) -> Dict[str, Dict]:
    """
    Get price data for multiple tickers
    Args:
        tickers_with_entities: List of (ticker, entity_id) tuples
    Returns:
        Dict mapping ticker to price data
    """
    results = {}
    
    for ticker, entity_id in tickers_with_entities:
        try:
            price_data = get_price_data(entity_id, ticker)
            results[ticker] = price_data
        except Exception as e:
            logger.error(f"Error fetching price for {ticker}: {e}")
            results[ticker] = {
                "price": None,
                "change": None,
                "currency": "USD",
                "timestamp": datetime.now(timezone.utc)
            }
    
    return results


def clear_cache():
    """Clear the entire price cache"""
    global price_cache
    price_cache = {}
    logger.info("Price cache cleared")


def clear_expired_cache():
    """Remove expired entries from cache"""
    global price_cache
    expired_keys = [
        ticker for ticker, data in price_cache.items()
        if not is_cache_valid(data)
    ]
    
    for key in expired_keys:
        del price_cache[key]
    
    if expired_keys:
        logger.info(f"Cleared {len(expired_keys)} expired price cache entries")


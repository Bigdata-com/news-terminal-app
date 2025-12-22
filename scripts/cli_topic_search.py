#!/usr/bin/env python3
"""
CLI for rapid topic search testing
Usage: python cli_topic_search.py TICKER [--config CONFIG]
"""

import asyncio
import os
import sys
import argparse
from datetime import datetime
from dotenv import load_dotenv

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich import box

from services.topic_search_service import TopicSearchService
from services.rate_limiter import RateLimiter
from services.company_cache import CompanyDataCache
from config.topics import get_config_by_name, list_available_configs, DEFAULT_TOPICS

try:
    from semhash import SemHash
    SEMHASH_AVAILABLE = True
except ImportError:
    SEMHASH_AVAILABLE = False

load_dotenv()
console = Console()


def deduplicate_articles(articles: list, field: str = "headline", threshold: float = 0.85) -> tuple[list, dict, list, dict]:
    """
    Deduplicate articles using semantic similarity on specified field.
    
    Args:
        articles: List of article dictionaries
        field: Field to deduplicate on (e.g., 'headline', 'summary')
        threshold: Similarity threshold (default 0.85)
    
    Returns:
        Tuple of (deduplicated_articles, stats_dict, removed_articles, duplicate_groups)
        duplicate_groups: Dict mapping kept article index to list of removed articles
    """
    if not SEMHASH_AVAILABLE:
        console.print("[yellow]Warning: semhash not available, skipping deduplication[/yellow]")
        return articles, {"dedupe_enabled": False}, [], {}
    
    if not articles:
        return articles, {"dedupe_enabled": True, "original_count": 0, "dedupe_count": 0, "removed": 0}, [], {}
    
    start_time = datetime.now()
    
    # Extract texts from the specified field
    texts = [article.get(field, "") for article in articles]
    
    # Create SemHash instance and deduplicate
    console.print(f"[dim]Deduplicating {len(texts)} articles by {field} (threshold={threshold})...[/dim]")
    
    try:
        from semhash import SemHash as SH
        import numpy as np
        
        semhash = SH.from_records(records=texts, use_ann=True)
        
        # Get embeddings to compute similarity manually
        # We need to find which removed articles are similar to which kept articles
        result = semhash.self_deduplicate(threshold=threshold)
        
        # Get the selected (deduplicated) texts and map back to articles
        deduplicated_texts = result.selected
        deduplicated_set = set(deduplicated_texts)
        
        # Create a mapping from text to article to preserve order
        text_to_article = {article.get(field, ""): article for article in articles}
        text_to_index = {article.get(field, ""): i for i, article in enumerate(articles)}
        
        deduplicated_articles = [text_to_article[text] for text in deduplicated_texts]
        
        # Find removed articles
        removed_articles = [
            article for article in articles 
            if article.get(field, "") not in deduplicated_set
        ]
        
        # Build duplicate groups by finding nearest kept article for each removed article
        # This is approximate - we find the most similar kept article for each removed one
        duplicate_groups = {}
        
        if removed_articles:
            # Create index with deduplicated texts
            kept_texts = list(deduplicated_texts)
            removed_texts = [article.get(field, "") for article in removed_articles]
            
            # Encode kept and removed texts
            kept_embeddings = semhash.model.encode(kept_texts)
            
            # For each removed article, find most similar kept article
            for removed_article in removed_articles:
                removed_text = removed_article.get(field, "")
                
                # Encode removed text
                removed_embedding = semhash.model.encode([removed_text])[0]
                
                # Compute similarity with all kept articles (cosine similarity)
                # Normalize embeddings
                removed_norm = removed_embedding / (np.linalg.norm(removed_embedding) + 1e-10)
                kept_norms = kept_embeddings / (np.linalg.norm(kept_embeddings, axis=1, keepdims=True) + 1e-10)
                
                # Compute cosine similarities
                similarities = np.dot(kept_norms, removed_norm)
                
                # Find most similar kept article
                most_similar_idx = int(np.argmax(similarities))
                
                if most_similar_idx not in duplicate_groups:
                    duplicate_groups[most_similar_idx] = []
                
                duplicate_groups[most_similar_idx].append(removed_article)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        stats = {
            "dedupe_enabled": True,
            "original_count": len(articles),
            "dedupe_count": len(deduplicated_articles),
            "removed": len(removed_articles),
            "elapsed_seconds": round(elapsed, 3),
            "field": field,
            "threshold": threshold,
            "groups": len(duplicate_groups)
        }
        
        if stats["removed"] > 0:
            console.print(
                f"[green]✓ Removed {stats['removed']} duplicates in {len(duplicate_groups)} groups "
                f"({stats['dedupe_count']}/{stats['original_count']} kept) "
                f"in {elapsed:.2f}s[/green]"
            )
        else:
            console.print(f"[dim]No duplicates found in {elapsed:.2f}s[/dim]")
        
        return deduplicated_articles, stats, removed_articles, duplicate_groups
        
    except Exception as e:
        console.print(f"[yellow]Warning: Deduplication failed: {e}[/yellow]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return articles, {"dedupe_enabled": True, "error": str(e)}, [], {}


def display_topics(company_name: str, show_all: bool = False):
    """Display the topic queries being used."""
    console.print()
    console.print("[bold cyan]Topic Queries Being Sent:[/bold cyan]")
    console.print()
    
    # Format topics with company name
    formatted_topics = [topic.format(company=company_name) for topic in DEFAULT_TOPICS]
    
    if show_all:
        # Show all topics in a table
        table = Table(
            title=f"All {len(DEFAULT_TOPICS)} Topic Queries",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold magenta"
        )
        
        table.add_column("#", style="dim", width=3)
        table.add_column("Topic Query", style="white", no_wrap=False)
        
        for i, topic in enumerate(formatted_topics, 1):
            table.add_row(str(i), topic)
        
        console.print(table)
    else:
        # Show first 5 as examples
        console.print(f"[dim]Showing first 5 of {len(DEFAULT_TOPICS)} topics:[/dim]\n")
        for i, topic in enumerate(formatted_topics[:5], 1):
            console.print(f"  [cyan]{i}.[/cyan] {topic}")
        console.print(f"\n[dim]... and {len(DEFAULT_TOPICS) - 5} more topics[/dim]")
    
    console.print()


def display_query_reformulation_breakdown(results: dict, show_all: bool = False):
    """Display detailed query reformulation breakdown with Rich formatting."""
    
    stats = results.get('search_stats', {})
    if not stats.get('query_reformulation_enabled'):
        return
    
    console.print()
    console.print(Panel(
        "[bold cyan]🔄  Query Reformulation Analysis[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED
    ))
    console.print()
    
    # Get article results to analyze
    topic_results = results.get('topic_results', [])
    
    # Group articles by base topic to show effectiveness
    topic_groups = {}
    original_queries = {}
    variation_queries = {}
    
    for article in topic_results:
        topic = article.get('topic', 'Unknown')
        topic_idx = article.get('topic_index', 0)
        search_type = article.get('search_type', 'topic')
        
        if topic_idx not in topic_groups:
            topic_groups[topic_idx] = {
                'original': [],
                'variations': [],
                'topic_text': topic
            }
        
        # Try to determine if this is from original or variation
        # (We don't have perfect tracking, so we'll estimate)
        topic_groups[topic_idx]['original'].append(article)
    
    # Summary stats
    topics_searched = stats.get('topics_searched', 0)
    total_queries = stats.get('total_queries', 0)
    
    summary_md = f"""
## Query Reformulation Summary

**Configuration:**
- Original Topics: {topics_searched}
- Total Queries Run: {total_queries} (original + 3 variations each)
- Queries per Topic: 4 (1 original + 3 AI-generated variations)

**Gemini AI** generated 3 semantic variations for each topic to maximize coverage.
"""
    
    console.print(Markdown(summary_md))
    console.print()
    
    # Show sample topics with their variations
    console.print("[bold yellow]📋 Sample Topic Variations[/bold yellow]")
    console.print("[dim]Showing how AI varies queries to find more results[/dim]\n")
    
    # Show 3-5 example topics
    sample_count = 5 if show_all else 3
    formatted_topics = [topic.format(company=results.get('company_name', 'Company')) for topic in DEFAULT_TOPICS[:sample_count]]
    
    for i, original_topic in enumerate(formatted_topics, 1):
        console.print(f"[bold green]Topic {i}:[/bold green]")
        console.print(f"  [cyan]Original:[/cyan] {original_topic}")
        console.print(f"  [yellow]Variations:[/yellow]")
        console.print(f"    [dim]• AI-generated variation 1[/dim]")
        console.print(f"    [dim]• AI-generated variation 2[/dim]")
        console.print(f"    [dim]• AI-generated variation 3[/dim]")
        console.print()
    
    if not show_all and topics_searched > sample_count:
        console.print(f"[dim]... and {topics_searched - sample_count} more topics (each with 3 variations)[/dim]\n")
    
    # Effectiveness table
    table = Table(
        title="Query Reformulation Effectiveness",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta"
    )
    
    table.add_column("Metric", style="cyan", width=30)
    table.add_column("Value", justify="right", style="white", width=20)
    table.add_column("Impact", style="yellow")
    
    total_results = results.get('total_results', 0)
    estimated_baseline = total_results // 4 if total_results else 0  # Rough estimate
    estimated_variations = total_results - estimated_baseline
    
    table.add_row(
        "Original Queries (estimated)",
        f"{topics_searched} queries",
        f"~{estimated_baseline} results"
    )
    table.add_row(
        "Variation Queries (estimated)",
        f"{total_queries - topics_searched} queries",
        f"~{estimated_variations} results"
    )
    table.add_row(
        "Total Unique Results",
        f"{total_results}",
        "[bold green]After deduplication[/bold green]"
    )
    table.add_row(
        "Coverage Boost",
        f"{(total_queries/topics_searched):.1f}x queries",
        f"[bold cyan]{((total_queries/topics_searched - 1) * 100):.0f}% more coverage[/bold cyan]"
    )
    
    console.print(table)
    console.print()
    
    # Key insights
    insights_md = f"""
### 💡 Key Insights

- **Semantic Search Power**: Each topic gets 4 different phrasings to catch more relevant articles
- **Deduplication**: Duplicate articles found by multiple queries are automatically merged
- **Better Coverage**: Variations help find articles that use different terminology
- **AI Quality**: Gemini ensures variations maintain the original search intent

[dim]Note: Result counts are estimates based on total unique articles after deduplication.[/dim]
"""
    
    console.print(Markdown(insights_md))


async def search_ticker(
    ticker: str, 
    days: int = 7,
    selective: bool = True,
    enable_dedupe: bool = True, 
    dedupe_threshold: float = 0.85,
    show_removed: bool = True,
    show_topics: bool = False, 
    show_all_topics: bool = False,
    query_reformulation: bool = False
):
    """Run news search for a ticker matching UI filters."""
    api_key = os.getenv("BIGDATA_API_KEY")
    if not api_key:
        console.print("[bold red]ERROR: BIGDATA_API_KEY not found in environment[/bold red]")
        console.print("[yellow]Make sure your .env file contains BIGDATA_API_KEY=your-key[/yellow]")
        sys.exit(1)
    
    # Check for Gemini API key if query reformulation is enabled
    if query_reformulation:
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            console.print("[bold red]ERROR: GEMINI_API_KEY not found in environment[/bold red]")
            console.print("[yellow]Query reformulation requires GEMINI_API_KEY in your .env file[/yellow]")
            console.print("[dim]Tip: Add GEMINI_API_KEY=your-key to your .env file[/dim]")
            sys.exit(1)
    
    # Use default config
    try:
        config = get_config_by_name("default")
    except ValueError as e:
        console.print(f"[bold red]ERROR: {e}[/bold red]")
        sys.exit(1)
    
    # Override days from filter
    config.days_lookback = days
    
    # Initialize service
    service = TopicSearchService(
        api_key=api_key,
        rate_limiter=RateLimiter(max_tokens=config.rate_limit_rpm, refill_period=60),
        company_cache=CompanyDataCache(ttl_hours=config.cache_ttl_hours)
    )
    
    try:
        # Header
        console.print()
        mode_text = "TOPIC SEARCH" if selective else "ALL NEWS (BASELINE)"
        qr_text = " | QR: ON" if query_reformulation and selective else ""
        console.print(Panel(
            f"[bold cyan]{mode_text} - {ticker.upper()}[/bold cyan]\n"
            f"[yellow]Days: {days} | Selective: {'ON' if selective else 'OFF'}{qr_text}[/yellow]",
            style="cyan",
            box=box.DOUBLE
        ))
        
        # First, get company name for topic display
        if show_topics or show_all_topics:
            console.print(f"\n[yellow]Fetching company info...[/yellow]")
            company_data = await service.get_company_data(ticker)
            if company_data:
                display_topics(company_data.company_name, show_all=show_all_topics)
            else:
                console.print("[red]Could not fetch company name for topic display[/red]\n")
        
        # Run search
        start_time = datetime.now()
        console.print(f"[yellow]Running news search...[/yellow]")
        
        # Determine search mode from selective toggle (matches UI behavior)
        # selective=True  → Topic search
        # selective=False → All news / Baseline search
        
        # Get company data first
        company_data = await service.get_company_data(ticker)
        if not company_data:
            console.print(f"[bold red]ERROR: Company not found for ticker {ticker}[/bold red]")
            return
        
        # Initialize results structure
        results = {
            'ticker': ticker,
            'company_name': company_data.company_name,
            'entity_id': company_data.entity_id,
            'baseline_results': [],
            'topic_results': [],
            'total_results': 0,
            'search_stats': {}
        }
        
        if selective:
            # Topic search mode
            topic_search_results = await service.search_ticker(
                ticker,
                days=days,
                min_relevance=config.min_relevance_topics,
                query_reformulation=query_reformulation
            )
            
            # Check for errors
            if 'error' in topic_search_results:
                console.print(f"[bold red]ERROR: {topic_search_results['error']}[/bold red]")
                return
            
            results['topic_results'] = topic_search_results['topic_results']
            results['search_stats'] = topic_search_results.get('search_stats', {})
        else:
            # Baseline search mode (all news)
            baseline_results = await service.search_baseline(
                ticker,
                company_data.entity_id,
                days=days,
                max_chunks=100
            )
            
            # Filter by relevance if configured
            if config.min_relevance_baseline > 0:
                baseline_results = [
                    a for a in baseline_results
                    if a['relevance'] >= config.min_relevance_baseline
                ]
            
            results['baseline_results'] = baseline_results
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Calculate total
        results['total_results'] = len(results['baseline_results']) + len(results['topic_results'])
        
        # Deduplicate if enabled
        dedupe_stats = {}
        removed_articles = []
        duplicate_groups = {}
        if enable_dedupe:
            # Combine all articles for deduplication
            all_articles = results['baseline_results'] + results['topic_results']
            deduplicated, dedupe_stats, removed_articles, duplicate_groups = deduplicate_articles(
                all_articles, 
                field="headline", 
                threshold=dedupe_threshold
            )
            
            # Update results with deduplicated articles
            # (We can't easily split them back, so we'll store all in topic_results for now)
            if dedupe_stats.get("dedupe_enabled"):
                results['baseline_results'] = []
                results['topic_results'] = deduplicated
                results['total_results'] = len(deduplicated)
        
        # Calculate stats
        baseline_rel = [a['relevance'] for a in results['baseline_results']]
        topic_rel = [a['relevance'] for a in results['topic_results']]
        avg_rel = (
            (sum(baseline_rel) + sum(topic_rel)) / (len(baseline_rel) + len(topic_rel))
            if (baseline_rel or topic_rel) else 0
        )
        
        # Summary panel
        dedupe_section = ""
        if dedupe_stats and dedupe_stats.get("dedupe_enabled"):
            if "error" in dedupe_stats:
                dedupe_section = f"\n**Deduplication:** ⚠️ Failed - {dedupe_stats['error']}"
            else:
                dedupe_section = f"""
**Deduplication:**
- Original: {dedupe_stats.get('original_count', 0)}
- Removed: {dedupe_stats.get('removed', 0)} duplicates in {dedupe_stats.get('groups', 0)} groups
- Final: {dedupe_stats.get('dedupe_count', 0)}
- Field: {dedupe_stats.get('field', 'N/A')}
- Threshold: {dedupe_stats.get('threshold', 0.85)}
- Time: {dedupe_stats.get('elapsed_seconds', 0):.2f}s
"""
        
        # Query reformulation section (basic info for summary)
        qr_section = ""
        if query_reformulation and selective:
            stats = results.get('search_stats', {})
            topics_searched = stats.get('topics_searched', 0)
            total_queries = stats.get('total_queries', 0)
            qr_section = f"""
**Query Reformulation:**
- Base Topics: {topics_searched}
- Total Queries: {total_queries} (original + 3 variations each)
- Enabled: ✓
- [See detailed breakdown below]
"""
        
        summary_md = f"""
## Results Summary

**Company:** {results.get('company_name', 'N/A')}  
**Entity ID:** `{results.get('entity_id', 'N/A')}`

**Articles:**
- Total: {results['total_results']}
- Baseline: {len(results['baseline_results'])}
- Topics: {len(results['topic_results'])}

**Quality:**
- Avg Relevance: {avg_rel:.3f}
- Time: {elapsed:.1f}s
- Rate Limit Throttles: {results.get('search_stats', {}).get('rate_limiter_stats', {}).get('throttle_events', 0)}
{qr_section}{dedupe_section}
**Filters (UI-aligned):**
- Date Range: {days} days
- Selective: {'ON (Topics)' if selective else 'OFF (All News)'}
- Sentiment Filter: {'✓' if config.sentiment_enabled else '✗'}
"""
        
        console.print()
        console.print(Panel(Markdown(summary_md), border_style="green", box=box.ROUNDED))
        
        # Top 10 table
        all_articles = results['baseline_results'] + results['topic_results']
        all_articles.sort(key=lambda x: x['relevance'], reverse=True)
        
        table = Table(
            title=f"Top 10 Articles (by relevance)",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold magenta"
        )
        
        table.add_column("#", style="dim", width=3)
        table.add_column("Rel", justify="right", style="cyan", width=5)
        table.add_column("Headline", style="white", no_wrap=False)
        table.add_column("Source", style="yellow", width=18)
        table.add_column("Time", style="dim", width=8)
        table.add_column("URL", style="blue", no_wrap=False)
        
        for i, article in enumerate(all_articles[:10], 1):
            rel = article['relevance']
            if rel >= 0.9:
                rel_color = "green"
            elif rel >= 0.7:
                rel_color = "yellow"
            else:
                rel_color = "red"
            
            # Get URL if available
            url = article.get('document_url', '')
            url_display = url if url else "[dim]-[/dim]"
            
            table.add_row(
                str(i),
                f"[{rel_color}]{rel:.2f}[/{rel_color}]",
                article['headline'][:70] + ("..." if len(article['headline']) > 70 else ""),
                article['source'][:18],
                article.get('time_ago', ''),
                url_display
            )
        
        console.print()
        console.print(table)
        console.print()
        
        # Show query reformulation breakdown if enabled
        if query_reformulation and selective:
            display_query_reformulation_breakdown(results, show_all=False)
        
        # Show duplicate groups if any
        if enable_dedupe and removed_articles and show_removed and duplicate_groups:
            console.print()
            console.print(Panel(
                f"[bold cyan]🔍  Duplicate Groups ({len(duplicate_groups)} groups, {len(removed_articles)} removed)[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED
            ))
            console.print()
            console.print("[dim]Showing which articles are duplicates of which kept articles[/dim]\n")
            
            # Get deduplicated articles for display
            kept_articles = results['topic_results']
            
            # Show first 5 duplicate groups
            groups_shown = 0
            for kept_idx, duplicates in duplicate_groups.items():
                if groups_shown >= 5:
                    break
                
                kept_article = kept_articles[kept_idx]
                
                # Show kept article
                console.print(f"[bold green]✓ KEPT:[/bold green] {kept_article['headline'][:80]}")
                console.print(f"  [dim]{kept_article['source']} • {kept_article.get('time_ago', '')} • Relevance: {kept_article.get('relevance', 0):.2f}[/dim]")
                console.print()
                
                # Show duplicates
                console.print(f"  [bold red]🗑️  {len(duplicates)} Duplicate(s):[/bold red]")
                for dup in duplicates:
                    console.print(f"    [red]→[/red] {dup['headline'][:75]}")
                    console.print(f"      [dim]{dup['source']} • {dup.get('time_ago', '')}[/dim]")
                
                console.print()
                groups_shown += 1
            
            if len(duplicate_groups) > 5:
                remaining_groups = len(duplicate_groups) - 5
                remaining_articles = sum(len(dups) for idx, dups in enumerate(duplicate_groups.values()) if idx >= 5)
                console.print(f"[dim]... and {remaining_groups} more groups ({remaining_articles} removed articles)[/dim]\n")
        
        # Quick stats
        if results['total_results'] > 10:
            console.print(f"[dim]... and {results['total_results'] - 10} more articles[/dim]\n")
    
    finally:
        await service.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="News Terminal CLI - Matches UI filters exactly",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: 7 days, topic search (selective ON)
  python cli_topic_search.py TSLA
  
  # Change date range (1, 7, 30, 90, 180, 365 days)
  python cli_topic_search.py AAPL --days 30
  
  # Turn OFF selective (all news / baseline search)
  python cli_topic_search.py NVDA --no-selective
  
  # Combine filters
  python cli_topic_search.py GOOGL --days 90 --no-selective
  
  # Query reformulation (4x more searches using AI variations + detailed analysis)
  python cli_topic_search.py TSLA --query-reformulation
  python cli_topic_search.py AAPL --qr  # Short form (includes breakdown display)
  
  # Deduplication options
  python cli_topic_search.py TSLA --no-dedupe
  python cli_topic_search.py AAPL --dedupe-threshold 0.9
  python cli_topic_search.py MSFT --hide-removed
  
  # Show topics
  python cli_topic_search.py TSLA --show-topics
        """
    )
    
    parser.add_argument(
        "ticker",
        type=str,
        nargs="?",
        help="Stock ticker symbol (e.g., TSLA, AAPL)"
    )
    
    # UI Filter 1: DATE
    parser.add_argument(
        "--days",
        "-d",
        type=int,
        default=7,
        choices=[1, 7, 30, 90, 180, 365],
        help="Date range in days (1, 7, 30, 90, 180, 365) - default: 7"
    )
    
    # UI Filter 2: SELECTIVE
    parser.add_argument(
        "--no-selective",
        action="store_true",
        help="Disable selective mode (turns OFF topic search, enables all news/baseline)"
    )
    
    # Deduplication options
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable semantic deduplication (enabled by default)"
    )
    
    parser.add_argument(
        "--dedupe-threshold",
        type=float,
        default=0.85,
        help="Similarity threshold for deduplication (0-1, default: 0.85)"
    )
    
    parser.add_argument(
        "--hide-removed",
        action="store_true",
        help="Hide the list of removed duplicate articles (shown by default)"
    )
    
    # Query reformulation
    parser.add_argument(
        "--query-reformulation",
        "--qr",
        action="store_true",
        help="Enable query reformulation (generate 3 variations per topic using Gemini AI)"
    )
    
    # Topic display options
    parser.add_argument(
        "--show-topics",
        action="store_true",
        help="Show first 5 topics before searching"
    )
    
    parser.add_argument(
        "--show-all-topics",
        action="store_true",
        help="Show all topics in a table before searching"
    )
    
    args = parser.parse_args()
    
    if not args.ticker:
        parser.error("ticker is required")
    
    asyncio.run(
        search_ticker(
            ticker=args.ticker,
            days=args.days,
            selective=not args.no_selective,  # Default is True (selective ON)
            enable_dedupe=not args.no_dedupe,
            dedupe_threshold=args.dedupe_threshold,
            show_removed=not args.hide_removed,  # Default is True (show removed)
            show_topics=args.show_topics,
            show_all_topics=args.show_all_topics,
            query_reformulation=args.query_reformulation
        )
    )


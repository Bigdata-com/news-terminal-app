#!/usr/bin/env python3
"""
CLI Report Generator - Full pipeline from news search to AI commentary
Usage: python cli_report_generator.py TICKER [options]

This script:
1. Runs topic search with query reformulation (4x coverage)
2. Generates executive briefs (one per topic)
3. Generates Wall Street desk note
4. Saves outputs to files for client delivery
"""

import asyncio
import os
import sys
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich import box

from services.topic_search_service import TopicSearchService
from services.report_service import ReportService
from services.rate_limiter import RateLimiter
from services.company_cache import CompanyDataCache
from config.topics import get_config_by_name

try:
    from semhash import SemHash
    SEMHASH_AVAILABLE = True
except ImportError:
    SEMHASH_AVAILABLE = False

load_dotenv()
console = Console()


def validate_environment() -> tuple[str, bool]:
    """
    Validate required environment variables are set.
    
    Returns:
        Tuple of (bigdata_api_key, has_gemini_auth)
    """
    api_key = os.getenv("BIGDATA_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    vertex_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    errors = []
    if not api_key:
        errors.append("BIGDATA_API_KEY not found")
    
    # Check for either Gemini API key OR Vertex AI credentials
    has_gemini_auth = bool(gemini_key or vertex_creds)
    if not has_gemini_auth:
        errors.append("GEMINI_API_KEY or GOOGLE_APPLICATION_CREDENTIALS not found")
    
    if errors:
        console.print("[bold red]ERROR: Missing required authentication[/bold red]")
        for error in errors:
            console.print(f"  • {error}")
        console.print("\n[yellow]Make sure your .env file contains:[/yellow]")
        console.print("  BIGDATA_API_KEY=your-bigdata-key")
        console.print("\n[yellow]And one of:[/yellow]")
        console.print("  GEMINI_API_KEY=your-gemini-key  [API Key auth]")
        console.print("  OR")
        console.print("  GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json  [Vertex AI auth]")
        sys.exit(1)
    
    return api_key, has_gemini_auth


def create_output_directory(output_dir: str) -> Path:
    """Create output directory if it doesn't exist."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_outputs(
    ticker: str,
    commentary: Any,
    news_response: Dict[str, Any],
    output_dir: Path,
    timestamp: str
) -> Dict[str, str]:
    """
    Save all outputs to files.
    
    Returns:
        Dict mapping output type to file path
    """
    files_saved = {}
    
    # 1. Save briefs (bullet points)
    briefs_path = output_dir / f"{ticker}_{timestamp}_briefs.txt"
    with open(briefs_path, 'w', encoding='utf-8') as f:
        f.write(f"EXECUTIVE BRIEFS - {commentary.company_name} ({ticker})\n")
        f.write(f"Generated: {commentary.generated_at}\n")
        f.write("=" * 80 + "\n\n")
        
        for brief in commentary.briefs:
            f.write(f"TOPIC: {brief.topic_name}\n")
            f.write(f"{brief.bullet_point}\n")
            if hasattr(brief, 'document_url') and brief.document_url:
                f.write(f"Source: {brief.document_url}\n")
            f.write("\n")
    
    files_saved['briefs'] = str(briefs_path)
    
    # 2. Save desk note
    desk_note_path = output_dir / f"{ticker}_{timestamp}_desk_note.txt"
    with open(desk_note_path, 'w', encoding='utf-8') as f:
        f.write(f"WALL STREET DESK NOTE - {commentary.company_name} ({ticker})\n")
        f.write(f"Generated: {commentary.generated_at}\n")
        f.write("=" * 80 + "\n\n")
        f.write(commentary.desk_note)
        f.write("\n")
    
    files_saved['desk_note'] = str(desk_note_path)
    
    # 3. Save full report as JSON
    full_report_path = output_dir / f"{ticker}_{timestamp}_full_report.json"
    
    # Build complete report
    report_data = {
        'ticker': ticker,
        'company_name': commentary.company_name,
        'generated_at': commentary.generated_at,
        'briefs': [
            {
                'company_name': b.company_name,
                'topic_name': b.topic_name,
                'bullet_point': b.bullet_point,
                'document_url': getattr(b, 'document_url', None)
            }
            for b in commentary.briefs
        ],
        'desk_note': commentary.desk_note,
        'metadata': {
            'total_articles': news_response.get('total_results', 0),
            'search_stats': news_response.get('search_stats', {}),
            'days_lookback': news_response.get('search_stats', {}).get('days_lookback', None)
        }
    }
    
    with open(full_report_path, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    files_saved['full_report'] = str(full_report_path)
    
    return files_saved


def display_briefs(commentary: Any):
    """Display executive briefs in formatted table."""
    console.print()
    console.print(Panel(
        f"[bold cyan]📋 EXECUTIVE BRIEFS[/bold cyan]\n"
        f"[yellow]{commentary.company_name} ({commentary.ticker})[/yellow]",
        border_style="cyan",
        box=box.ROUNDED
    ))
    console.print()
    
    # Create table for briefs
    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="bold magenta",
        padding=(0, 1)
    )
    
    table.add_column("#", style="dim", width=3)
    table.add_column("Topic", style="cyan", width=30)
    table.add_column("Brief", style="white", no_wrap=False)
    
    for i, brief in enumerate(commentary.briefs, 1):
        table.add_row(
            str(i),
            brief.topic_name,
            brief.bullet_point
        )
    
    console.print(table)
    console.print()


def display_desk_note(commentary: Any):
    """Display Wall Street desk note."""
    console.print()
    console.print(Panel(
        f"[bold cyan]📰 WALL STREET DESK NOTE[/bold cyan]\n"
        f"[yellow]{commentary.company_name} ({commentary.ticker})[/yellow]",
        border_style="cyan",
        box=box.ROUNDED
    ))
    console.print()
    
    # Display as markdown for better formatting
    desk_note_md = f"""
{commentary.desk_note}
"""
    console.print(Markdown(desk_note_md))
    console.print()


def display_articles_table(news_response: Dict[str, Any], limit: int = 20):
    """Display raw articles in a table."""
    articles = news_response.get('topic_results', [])
    
    if not articles:
        console.print("[yellow]No articles found[/yellow]")
        return
    
    console.print()
    console.print(Panel(
        f"[bold cyan]📰 RAW ARTICLES[/bold cyan]\n"
        f"[yellow]Showing top {min(limit, len(articles))} of {len(articles)} articles[/yellow]",
        border_style="cyan",
        box=box.ROUNDED
    ))
    console.print()
    
    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="bold magenta"
    )
    
    table.add_column("#", style="dim", width=3)
    table.add_column("Rel", justify="right", style="cyan", width=5)
    table.add_column("Topic", style="yellow", width=30, no_wrap=False)
    table.add_column("Headline", style="white", no_wrap=False)
    table.add_column("Source", style="dim", width=18)
    
    # Sort by relevance
    sorted_articles = sorted(articles, key=lambda x: x.get('relevance', 0), reverse=True)
    
    for i, article in enumerate(sorted_articles[:limit], 1):
        rel = article.get('relevance', 0)
        if rel >= 0.9:
            rel_color = "green"
        elif rel >= 0.7:
            rel_color = "yellow"
        else:
            rel_color = "red"
        
        topic = article.get('topic', 'Unknown')[:30]
        headline = article.get('headline', 'No headline')[:60]
        source = article.get('source', 'Unknown')[:18]
        
        table.add_row(
            str(i),
            f"[{rel_color}]{rel:.2f}[/{rel_color}]",
            topic,
            headline + ("..." if len(article.get('headline', '')) > 60 else ""),
            source
        )
    
    console.print(table)
    
    if len(articles) > limit:
        console.print(f"\n[dim]... and {len(articles) - limit} more articles[/dim]\n")


async def generate_report(
    ticker: str,
    days: int = 7,
    output_dir: Optional[str] = None,
    save_files: bool = True,
    show_articles: bool = False,
    verbose: bool = False,
    enable_query_reformulation: bool = True
):
    """
    Main function to generate complete report.
    
    Args:
        ticker: Stock ticker symbol
        days: Days of news to search
        output_dir: Directory to save outputs (default: ./output)
        save_files: Whether to save files
        show_articles: Whether to display raw articles
        verbose: Show detailed progress
        enable_query_reformulation: Enable query reformulation (default: True)
    """
    # Validate environment
    api_key, has_gemini_auth = validate_environment()
    
    # Create output directory
    if save_files:
        if output_dir is None:
            output_dir = "output"
        output_path = create_output_directory(output_dir)
    
    # Get config
    try:
        config = get_config_by_name("default")
    except ValueError as e:
        console.print(f"[bold red]ERROR: {e}[/bold red]")
        sys.exit(1)
    
    config.days_lookback = days
    
    # Initialize services
    topic_service = TopicSearchService(
        api_key=api_key,
        rate_limiter=RateLimiter(max_tokens=config.rate_limit_rpm, refill_period=60),
        company_cache=CompanyDataCache(ttl_hours=config.cache_ttl_hours)
    )
    
    report_service = ReportService()
    
    try:
        # Header
        console.print()
        qr_status = "ON" if enable_query_reformulation else "OFF"
        console.print(Panel(
            f"[bold cyan]📊 AI REPORT GENERATOR[/bold cyan]\n"
            f"[yellow]Ticker: {ticker.upper()} | Days: {days} | Query Reformulation: {qr_status}[/yellow]",
            style="cyan",
            box=box.DOUBLE
        ))
        console.print()
        
        # PHASE 1: Topic Search
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            console=console
        ) as progress:
            task1 = progress.add_task(
                f"[1/3] Running topic search{' with query reformulation' if enable_query_reformulation else ''}...",
                total=None
            )
            
            start_time = datetime.now()
            
            # Get company data
            company_data = await topic_service.get_company_data(ticker)
            if not company_data:
                console.print(f"[bold red]ERROR: Company not found for ticker {ticker}[/bold red]")
                sys.exit(1)
            
            # Run topic search
            news_response = await topic_service.search_ticker(
                ticker,
                days=days,
                min_relevance=config.min_relevance_topics,
                query_reformulation=enable_query_reformulation
            )
            
            if 'error' in news_response:
                console.print(f"[bold red]ERROR: {news_response['error']}[/bold red]")
                sys.exit(1)
            
            search_elapsed = (datetime.now() - start_time).total_seconds()
            progress.update(task1, completed=True)
        
        # Display search summary
        stats = news_response.get('search_stats', {})
        total_articles = len(news_response.get('topic_results', []))
        
        search_summary = f"""
## Search Complete ✓

**Company:** {company_data.company_name}  
**Articles Found:** {total_articles}  
**Topics Searched:** {stats.get('topics_searched', 0)}  
**Total Queries:** {stats.get('total_queries', 0)} {'(original + 3 variations each)' if enable_query_reformulation else ''}  
**Time:** {search_elapsed:.1f}s  
"""
        
        console.print(Panel(Markdown(search_summary), border_style="green", box=box.ROUNDED))
        
        if total_articles == 0:
            console.print("[yellow]No articles found. Cannot generate report.[/yellow]")
            return
        
        # Show articles if requested
        if show_articles:
            display_articles_table(news_response, limit=20)
        
        # PHASE 2: Generate Briefs
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            console=console
        ) as progress:
            task2 = progress.add_task(
                "[2/3] Generating executive briefs with Gemini AI...",
                total=None
            )
            
            briefs_start = datetime.now()
            commentary = await report_service.generate_commentary(news_response)
            briefs_elapsed = (datetime.now() - briefs_start).total_seconds()
            
            progress.update(task2, completed=True)
        
        console.print(f"[green]✓ Generated {len(commentary.briefs)} briefs in {briefs_elapsed:.1f}s[/green]\n")
        
        # Display briefs
        display_briefs(commentary)
        
        # Display desk note
        display_desk_note(commentary)
        
        # PHASE 3: Save files
        if save_files:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                console=console
            ) as progress:
                task3 = progress.add_task(
                    "[3/3] Saving outputs to files...",
                    total=None
                )
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                files_saved = save_outputs(
                    ticker.upper(),
                    commentary,
                    news_response,
                    output_path,
                    timestamp
                )
                
                progress.update(task3, completed=True)
            
            # Display saved files
            console.print()
            console.print(Panel(
                "[bold green]📁 FILES SAVED[/bold green]",
                border_style="green",
                box=box.ROUNDED
            ))
            console.print()
            
            for output_type, file_path in files_saved.items():
                icon = {
                    'briefs': '📋',
                    'desk_note': '📰',
                    'full_report': '📊'
                }.get(output_type, '📄')
                
                console.print(f"  {icon} [cyan]{output_type:12}[/cyan] → [yellow]{file_path}[/yellow]")
            
            console.print()
        
        # Final summary
        total_elapsed = (datetime.now() - start_time).total_seconds()
        
        summary = f"""
## 🎉 Report Generation Complete

**Total Time:** {total_elapsed:.1f}s  
**Articles Processed:** {total_articles}  
**Briefs Generated:** {len(commentary.briefs)}  
**Desk Note:** ✓ Generated  
{'**Files Saved:** ' + str(len(files_saved)) if save_files else '**Files:** Not saved (--no-save)'}

[dim]Ready to send to client![/dim]
"""
        
        console.print(Panel(Markdown(summary), border_style="green", box=box.ROUNDED))
        console.print()
    
    finally:
        await topic_service.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI Report Generator - Complete pipeline from news search to commentary",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: 7 days, query reformulation ON, saves to ./output/
  python cli_report_generator.py TSLA
  
  # Custom date range (1, 7, 30, 90, 180, 365 days)
  python cli_report_generator.py AAPL --days 30
  
  # Custom output directory
  python cli_report_generator.py NVDA --output-dir ~/client_reports/
  
  # Display only (no file save)
  python cli_report_generator.py GOOGL --no-save
  
  # Show raw articles + commentary
  python cli_report_generator.py MSFT --show-articles
  
  # Without query reformulation (faster, less coverage)
  python cli_report_generator.py AMZN --no-query-reformulation
  
  # Full verbose mode
  python cli_report_generator.py META --days 90 --show-articles --verbose

Output Files:
  {TICKER}_{timestamp}_briefs.txt      - Executive bullet points
  {TICKER}_{timestamp}_desk_note.txt   - Wall Street desk note
  {TICKER}_{timestamp}_full_report.json - Complete data (JSON)

Requirements:
  - BIGDATA_API_KEY in .env file
  - GEMINI_API_KEY in .env file
        """
    )
    
    parser.add_argument(
        "ticker",
        type=str,
        nargs="?",
        help="Stock ticker symbol (e.g., TSLA, AAPL, NVDA)"
    )
    
    parser.add_argument(
        "--days",
        "-d",
        type=int,
        default=7,
        choices=[1, 7, 30, 90, 180, 365],
        help="Date range in days (default: 7)"
    )
    
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default="output",
        help="Directory to save output files (default: ./output/)"
    )
    
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save files, display only"
    )
    
    parser.add_argument(
        "--show-articles",
        "-a",
        action="store_true",
        help="Display raw articles table"
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed progress and debug info"
    )
    
    parser.add_argument(
        "--no-query-reformulation",
        "--no-qr",
        action="store_true",
        help="Disable query reformulation (faster but less coverage)"
    )
    
    args = parser.parse_args()
    
    if not args.ticker:
        parser.error("ticker is required")
    
    # Run the generator
    asyncio.run(
        generate_report(
            ticker=args.ticker,
            days=args.days,
            output_dir=args.output_dir,
            save_files=not args.no_save,
            show_articles=args.show_articles,
            verbose=args.verbose,
            enable_query_reformulation=not args.no_query_reformulation
        )
    )


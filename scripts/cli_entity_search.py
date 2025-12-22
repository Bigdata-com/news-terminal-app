#!/usr/bin/env python3
"""
CLI for testing entity/company search via Knowledge Graph API
Usage: python cli_entity_search.py QUERY
"""

import os
import sys
import argparse
import requests
from dotenv import load_dotenv

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich import box

load_dotenv()
console = Console()


def search_entities(query: str, entity_type: str = "PUBLIC"):
    """Search for entities using Knowledge Graph API."""
    api_key = os.getenv("BIGDATA_API_KEY")
    if not api_key:
        console.print("[bold red]ERROR: BIGDATA_API_KEY not found[/bold red]")
        sys.exit(1)
    
    base_url = os.getenv("BIGDATA_BASE_URL", "https://api.bigdata.com/v1")
    
    # Header
    console.print()
    console.print(Panel(
        f"[bold cyan]Entity Search[/bold cyan]\n"
        f"[yellow]Query: {query}[/yellow]\n"
        f"[yellow]Type: {entity_type}[/yellow]",
        style="cyan",
        box=box.DOUBLE
    ))
    
    console.print("\n[yellow]Searching Knowledge Graph...[/yellow]\n")
    
    try:
        response = requests.post(
            f"{base_url}/knowledge-graph/companies",
            headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json"
            },
            json={
                "query": query,
                "types": [entity_type]
            },
            timeout=30
        )
        
        if response.status_code != 200:
            console.print(f"[bold red]API Error: {response.status_code}[/bold red]")
            console.print(f"[red]{response.text}[/red]\n")
            sys.exit(1)
        
        data = response.json()
        results = data.get("results", [])
        
        if not results:
            console.print(f"[yellow]No results found for query: {query}[/yellow]\n")
            return
        
        # Summary
        summary_md = f"""
## Search Results

**Query:** {query}  
**Results Found:** {len(results)}  
**Showing:** Top {min(len(results), 10)}
"""
        
        console.print(Panel(Markdown(summary_md), border_style="green", box=box.ROUNDED))
        
        # Results table
        table = Table(
            title=f"Top {min(len(results), 10)} Companies",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold magenta"
        )
        
        table.add_column("#", style="dim", width=3)
        table.add_column("Entity ID", style="cyan", width=12)
        table.add_column("Company Name", style="white", width=40, no_wrap=False)
        table.add_column("Ticker", style="yellow", width=10)
        table.add_column("Type", style="green", width=10)
        
        for i, company in enumerate(results[:10], 1):
            entity_id = company.get("id", "N/A")
            name = company.get("name", "N/A")
            ticker = company.get("ticker", "N/A")
            comp_type = company.get("type", "N/A")
            
            # Highlight exact ticker matches
            if ticker.upper() == query.upper():
                name_style = "[bold green]"
            else:
                name_style = ""
            
            table.add_row(
                str(i),
                entity_id,
                f"{name_style}{name}",
                ticker if ticker != "N/A" else "[dim]N/A[/dim]",
                comp_type
            )
        
        console.print()
        console.print(table)
        console.print()
        
        # Show best match details
        best_match = results[0]
        detail_md = f"""
## Best Match Details

**Entity ID:** `{best_match.get('id', 'N/A')}`  
**Name:** {best_match.get('name', 'N/A')}  
**Ticker:** {best_match.get('ticker', 'N/A')}  
**Type:** {best_match.get('type', 'N/A')}

**Use this Entity ID for news searches**
"""
        
        console.print(Panel(
            Markdown(detail_md),
            title="[bold cyan]Best Match[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED
        ))
        
        if len(results) > 10:
            console.print(f"\n[dim]... and {len(results) - 10} more results[/dim]")
        
        console.print()
    
    except requests.RequestException as e:
        console.print(f"[bold red]Request Error: {str(e)}[/bold red]\n")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]\n")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test entity/company search using Knowledge Graph API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli_entity_search.py TSLA
  python cli_entity_search.py "Tesla"
  python cli_entity_search.py AAPL --type PUBLIC
  python cli_entity_search.py "Apple Inc"
  python cli_entity_search.py MSFT
        """
    )
    
    parser.add_argument(
        "query",
        type=str,
        help="Ticker symbol or company name to search"
    )
    
    parser.add_argument(
        "--type",
        "-t",
        type=str,
        default="PUBLIC",
        choices=["PUBLIC", "PRIVATE", "ALL"],
        help="Entity type filter (default: PUBLIC)"
    )
    
    args = parser.parse_args()
    
    search_entities(args.query, args.type)


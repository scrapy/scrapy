"""
Advanced Rich utilities for Scrapy terminal output.
"""

from __future__ import annotations

from typing import Any, Dict

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from scrapy.utils.console import get_console


def print_spider_stats(stats: Dict[str, Any], spider_name: str = "Unknown", reason: str | None = None) -> None:
    """Print spider statistics in a formatted table.

    Args:
        stats: Dictionary of statistics
        spider_name: Name of the spider
        reason: Reason for spider completion
    """
    console = get_console()

    # Group stats by category
    categorized_stats = {
        "Requests": {},
        "Responses": {},
        "Items": {},
        "Errors": {},
        "Other": {}
    }

    for key, value in stats.items():
        if "request" in key.lower():
            categorized_stats["Requests"][key] = value
        elif "response" in key.lower():
            categorized_stats["Responses"][key] = value
        elif "item" in key.lower():
            categorized_stats["Items"][key] = value
        elif "error" in key.lower() or "exception" in key.lower():
            categorized_stats["Errors"][key] = value
        else:
            categorized_stats["Other"][key] = value

    # Create main info panel
    info_text = Text()
    info_text.append("Spider: ", style="info")
    info_text.append(spider_name, style="spider")
    if reason:
        info_text.append("\nFinished: ", style="info")
        info_text.append(reason, style="warning")

    panel = Panel(info_text, title="[bold green]Crawl Summary[/bold green]", border_style="green")
    console.print(panel)

    # Print categorized stats
    for category, cat_stats in categorized_stats.items():
        if not cat_stats:
            continue

        table = Table(title=f"[bold cyan]{category}[/bold cyan]", show_header=True, header_style="bold yellow")
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="green", justify="right")

        for key, value in sorted(cat_stats.items()):
            # Format large numbers with commas
            if isinstance(value, int) and value > 999:
                formatted_value = f"{value:,}"
            else:
                formatted_value = str(value)
            table.add_row(key, formatted_value)

        console.print(table)


def print_error_summary(errors: list[str], warnings: list[str] | None = None) -> None:
    """Print error and warning summary in formatted panels.

    Args:
        errors: List of error messages
        warnings: List of warning messages (optional)
    """
    console = get_console()

    if errors:
        error_text = Text("\n".join(errors), style="error")
        error_panel = Panel(error_text, title="[bold red]Errors[/bold red]", border_style="red")
        console.print(error_panel)

    if warnings:
        warning_text = Text("\n".join(warnings), style="warning")
        warning_panel = Panel(warning_text, title="[bold yellow]Warnings[/bold yellow]", border_style="yellow")
        console.print(warning_panel)


def print_spider_list(spiders: list[str], title: str = "Available Spiders") -> None:
    """Print a formatted list of spiders.

    Args:
        spiders: List of spider names
        title: Title for the spider list
    """
    console = get_console(use_stderr=False)

    if not spiders:
        console.print("[warning]No spiders found[/warning]")
        return

    table = Table(title=f"[bold green]{title}[/bold green]", show_header=False)
    table.add_column("Spider", style="spider")

    for spider in sorted(spiders):
        table.add_row(f"🕷️  {spider}")

    console.print(table)


def format_url(url: str) -> str:
    """Format a URL with rich styling.

    Args:
        url: URL to format

    Returns:
        Formatted URL string with rich markup
    """
    return f"[url]{url}[/url]"


def format_file_path(path: str) -> str:
    """Format a file path with rich styling.

    Args:
        path: File path to format

    Returns:
        Formatted path string with rich markup
    """
    return f"[filename]{path}[/filename]"


def format_number(number: int | float) -> str:
    """Format a number with rich styling and comma separators.

    Args:
        number: Number to format

    Returns:
        Formatted number string with rich markup
    """
    if isinstance(number, int) and number > 999:
        return f"[number]{number:,}[/number]"
    return f"[number]{number}[/number]"
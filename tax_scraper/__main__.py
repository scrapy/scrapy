"""
CLI interface for the tax scraper.

Usage:
    python -m tax_scraper scrape --site simic
    python -m tax_scraper scrape --all
    python -m tax_scraper list
    python -m tax_scraper info simic
"""

import argparse
import sys
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog="tax_scraper",
        description="Slovenian Tax Knowledge Scraper - Extract tax content for AI training",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Run scrapers")
    scrape_parser.add_argument(
        "--site", "-s",
        type=str,
        help="Spider name to run (use 'list' command to see available)",
    )
    scrape_parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Run all available spiders",
    )
    scrape_parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="./output",
        help="Output directory (default: ./output)",
    )
    scrape_parser.add_argument(
        "--format", "-f",
        choices=["json", "jsonl"],
        default="jsonl",
        help="Output format (default: jsonl)",
    )
    scrape_parser.add_argument(
        "--filter-tax",
        action="store_true",
        help="Only keep tax-related content",
    )
    scrape_parser.add_argument(
        "--log-level", "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List available spiders")
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # Info command
    info_parser = subparsers.add_parser("info", help="Show spider information")
    info_parser.add_argument("spider", help="Spider name")

    # Results command
    results_parser = subparsers.add_parser("results", help="View scraped results")
    results_parser.add_argument(
        "--dir", "-d",
        type=str,
        default="./output",
        help="Output directory to scan",
    )
    results_parser.add_argument(
        "--file", "-f",
        type=str,
        help="Specific file to view",
    )
    results_parser.add_argument(
        "--limit", "-n",
        type=int,
        default=5,
        help="Number of items to show (default: 5)",
    )

    args = parser.parse_args()

    if args.command == "scrape":
        cmd_scrape(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "results":
        cmd_results(args)
    else:
        parser.print_help()
        sys.exit(1)


def cmd_scrape(args):
    """Run the scraper."""
    from .api import TaxScraper
    from .spiders.registry import SpiderRegistry

    if not args.site and not args.all:
        print("Error: Specify --site or --all")
        sys.exit(1)

    scraper = TaxScraper(
        output_dir=args.output_dir,
        output_format=args.format,
        filter_non_tax=args.filter_tax,
        log_level=args.log_level,
    )

    if args.all:
        print("Running all spiders...")
        spiders = SpiderRegistry.names()
        for spider_name in spiders:
            print(f"\n{'='*50}")
            print(f"Running: {spider_name}")
            print('='*50)
            try:
                results = scraper.scrape(spider_name)
                print(f"Scraped {len(results)} items")
            except Exception as e:
                print(f"Error: {e}")
    else:
        print(f"Running spider: {args.site}")
        try:
            results = scraper.scrape(args.site)
            print(f"\nScraped {len(results)} items")
            print(f"Output: {args.output_dir}")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error during scraping: {e}")
            sys.exit(1)


def cmd_list(args):
    """List available spiders."""
    from .spiders.registry import SpiderRegistry

    # Ensure spiders are imported
    from . import spiders  # noqa: F401

    spider_list = SpiderRegistry.list_all()

    if args.json:
        print(json.dumps(spider_list, indent=2))
    else:
        print("\nAvailable spiders:")
        print("-" * 60)
        for spider in spider_list:
            domains = ", ".join(spider["domains"]) if spider["domains"] else "N/A"
            print(f"  {spider['name']:<12} - {domains}")
        print("-" * 60)
        print(f"\nTotal: {len(spider_list)} spiders")
        print("\nUsage: python -m tax_scraper scrape --site <name>")


def cmd_info(args):
    """Show spider information."""
    from .spiders.registry import SpiderRegistry

    # Ensure spiders are imported
    from . import spiders  # noqa: F401

    spider_class = SpiderRegistry.get(args.spider)
    if not spider_class:
        print(f"Spider '{args.spider}' not found")
        available = SpiderRegistry.names()
        print(f"Available: {', '.join(available)}")
        sys.exit(1)

    print(f"\nSpider: {args.spider}")
    print("-" * 40)
    print(f"Class: {spider_class.__name__}")
    print(f"Domains: {', '.join(getattr(spider_class, 'allowed_domains', []))}")
    print(f"Start URLs: {getattr(spider_class, 'start_urls', [])}")
    print(f"\nDescription:")
    print(spider_class.__doc__ or "No description available")


def cmd_results(args):
    """View scraped results."""
    output_dir = Path(args.dir)

    if args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"File not found: {args.file}")
            sys.exit(1)
        show_file_contents(filepath, args.limit)
    else:
        # List all output files
        files = list(output_dir.glob("*.json")) + list(output_dir.glob("*.jsonl"))
        if not files:
            print(f"No output files in {output_dir}")
            return

        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        print(f"\nOutput files in {output_dir}:")
        print("-" * 60)
        for f in files[:10]:
            size = f.stat().st_size
            size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
            print(f"  {f.name:<40} {size_str:>10}")

        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more")

        print(f"\nTo view: python -m tax_scraper results --file <path>")


def show_file_contents(filepath: Path, limit: int):
    """Display contents of a results file."""
    items = []

    if filepath.suffix == ".jsonl":
        with open(filepath, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= limit:
                    break
                if line.strip():
                    items.append(json.loads(line))
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                items = data[:limit]
            else:
                items = [data]

    print(f"\nShowing {len(items)} items from {filepath.name}:")
    print("=" * 60)

    for i, item in enumerate(items, 1):
        print(f"\n[{i}] {item.get('title', 'No title')}")
        print(f"    URL: {item.get('url', 'N/A')}")
        print(f"    Category: {item.get('category', 'N/A')}")
        print(f"    Topics: {', '.join(item.get('tax_topics', []))}")
        summary = item.get('summary', '')[:200]
        if summary:
            print(f"    Summary: {summary}...")


if __name__ == "__main__":
    main()

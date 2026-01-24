"""
Python API for integrating the tax scraper into applications.

Usage:
    from tax_scraper import TaxScraper

    # Initialize
    scraper = TaxScraper(output_dir="./data")

    # Scrape specific site
    results = scraper.scrape("simic")

    # Scrape all configured sites
    all_results = scraper.scrape_all()

    # Get available spiders
    spiders = scraper.list_spiders()
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

# Add parent directory to path for imports when used standalone
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from .spiders.registry import SpiderRegistry, list_spiders as registry_list_spiders
from .settings import get_settings


class TaxScraper:
    """
    Main API class for the tax knowledge scraper.

    Provides a clean interface for scraping tax content that can be
    easily integrated into other Python applications.
    """

    def __init__(
        self,
        output_dir: str = "./output",
        output_format: str = "jsonl",
        filter_non_tax: bool = False,
        log_level: str = "INFO",
    ):
        """
        Initialize the tax scraper.

        Args:
            output_dir: Directory for scraped data output
            output_format: Output format ('json' or 'jsonl')
            filter_non_tax: If True, only keep tax-related content
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        self.output_dir = Path(output_dir)
        self.output_format = output_format
        self.filter_non_tax = filter_non_tax
        self.log_level = log_level

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Import spiders to register them
        self._import_spiders()

    def _import_spiders(self):
        """Import all spiders to ensure they're registered."""
        from . import spiders  # noqa: F401

    def _get_process(self) -> CrawlerProcess:
        """Create a configured CrawlerProcess."""
        settings = get_settings()
        settings.update({
            "OUTPUT_DIR": str(self.output_dir),
            "OUTPUT_FORMAT": self.output_format,
            "FILTER_NON_TAX": self.filter_non_tax,
            "LOG_LEVEL": self.log_level,
        })
        return CrawlerProcess(settings)

    def scrape(
        self,
        spider_name: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Run a specific spider and return results.

        Args:
            spider_name: Name of the spider to run
            **kwargs: Additional arguments passed to the spider

        Returns:
            List of scraped items as dictionaries

        Raises:
            ValueError: If spider_name is not found
        """
        spider_class = SpiderRegistry.get(spider_name)
        if not spider_class:
            available = SpiderRegistry.names()
            raise ValueError(
                f"Spider '{spider_name}' not found. "
                f"Available: {', '.join(available)}"
            )

        process = self._get_process()
        results = []

        # Collect items
        def collect_item(item, response, spider):
            results.append(dict(item))

        # Connect item signal
        from scrapy import signals
        crawler = process.create_crawler(spider_class)
        crawler.signals.connect(collect_item, signal=signals.item_scraped)

        process.crawl(crawler, **kwargs)
        process.start()

        return results

    def scrape_async(
        self,
        spider_name: str,
        callback=None,
        **kwargs
    ) -> str:
        """
        Run a spider asynchronously and return the output file path.

        Useful for long-running scrapes in web applications.

        Args:
            spider_name: Name of the spider to run
            callback: Optional callback function(results) when complete
            **kwargs: Additional arguments passed to the spider

        Returns:
            Path to the output file
        """
        spider_class = SpiderRegistry.get(spider_name)
        if not spider_class:
            raise ValueError(f"Spider '{spider_name}' not found")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"{spider_name}_{timestamp}.{self.output_format}"

        # Run in subprocess to avoid reactor issues
        import subprocess
        cmd = [
            sys.executable, "-m", "tax_scraper",
            "scrape", "--site", spider_name,
            "--output-dir", str(self.output_dir),
            "--format", self.output_format,
        ]

        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return str(output_file)

    def scrape_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Run all registered spiders.

        Returns:
            Dict mapping spider names to their results
        """
        all_results = {}
        for spider_name in SpiderRegistry.names():
            try:
                results = self.scrape(spider_name)
                all_results[spider_name] = results
            except Exception as e:
                all_results[spider_name] = {"error": str(e)}

        return all_results

    def list_spiders(self) -> List[Dict[str, str]]:
        """
        Get list of available spiders.

        Returns:
            List of spider info dictionaries
        """
        return registry_list_spiders()

    def get_output_files(self) -> List[Path]:
        """
        Get list of output files in the output directory.

        Returns:
            List of output file paths
        """
        patterns = ["*.json", "*.jsonl"]
        files = []
        for pattern in patterns:
            files.extend(self.output_dir.glob(pattern))
        return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)

    def load_results(self, filepath: str) -> List[Dict[str, Any]]:
        """
        Load results from a JSON/JSONL file.

        Args:
            filepath: Path to the results file

        Returns:
            List of items
        """
        filepath = Path(filepath)
        items = []

        if filepath.suffix == ".jsonl":
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        items.append(json.loads(line))
        else:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    items = data
                else:
                    items = [data]

        return items


# Convenience functions for quick usage
def scrape_site(
    spider_name: str,
    output_dir: str = "./output",
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Quick function to scrape a single site.

    Args:
        spider_name: Name of the spider
        output_dir: Output directory
        **kwargs: Additional spider arguments

    Returns:
        List of scraped items
    """
    scraper = TaxScraper(output_dir=output_dir)
    return scraper.scrape(spider_name, **kwargs)


def scrape_all(output_dir: str = "./output") -> Dict[str, List[Dict[str, Any]]]:
    """
    Quick function to scrape all configured sites.

    Args:
        output_dir: Output directory

    Returns:
        Dict mapping spider names to results
    """
    scraper = TaxScraper(output_dir=output_dir)
    return scraper.scrape_all()


def get_available_spiders() -> List[str]:
    """Get list of available spider names."""
    # Ensure spiders are imported
    from . import spiders  # noqa: F401
    return SpiderRegistry.names()

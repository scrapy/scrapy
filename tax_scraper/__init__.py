"""
Slovenian Tax Knowledge Scraper

A modular web scraper for collecting tax-related content from Slovenian websites.
Designed for building AI training datasets for tax advisory applications.

Usage:
    # As CLI
    python -m tax_scraper scrape --site simic
    python -m tax_scraper scrape --all

    # As module in your app
    from tax_scraper import TaxScraper

    scraper = TaxScraper(output_dir="./data")
    results = scraper.scrape("simic")
    results = scraper.scrape_all()
"""

from .api import TaxScraper, scrape_site, scrape_all, get_available_spiders

__version__ = "0.1.0"
__all__ = ["TaxScraper", "scrape_site", "scrape_all", "get_available_spiders"]

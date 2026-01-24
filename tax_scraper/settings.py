"""
Scrapy settings for the tax scraper.
"""

from pathlib import Path


def get_settings():
    """
    Return Scrapy settings as a dict.

    Can be customized via environment variables or by modifying this function.
    """
    return {
        # Basic settings
        "BOT_NAME": "tax_scraper",
        "SPIDER_MODULES": ["tax_scraper.spiders"],
        "NEWSPIDER_MODULE": "tax_scraper.spiders",

        # Crawl responsibly
        "ROBOTSTXT_OBEY": True,
        "CONCURRENT_REQUESTS": 4,
        "DOWNLOAD_DELAY": 1,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,

        # Cookies and caching
        "COOKIES_ENABLED": False,
        "HTTPCACHE_ENABLED": True,
        "HTTPCACHE_EXPIRATION_SECS": 86400,  # 24 hours
        "HTTPCACHE_DIR": ".scrapy_cache",

        # User agent and headers
        "USER_AGENT": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sl,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
        },

        # Retry settings
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 3,
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429],

        # Pipelines
        "ITEM_PIPELINES": {
            "tax_scraper.core.pipelines.DuplicateFilterPipeline": 100,
            "tax_scraper.core.pipelines.TaxContentPipeline": 200,
            "tax_scraper.core.pipelines.JsonExportPipeline": 900,
        },

        # Custom settings
        "OUTPUT_DIR": "./output",
        "OUTPUT_FORMAT": "jsonl",  # 'json' or 'jsonl'
        "MIN_CONTENT_LENGTH": 100,
        "FILTER_NON_TAX": False,

        # Logging
        "LOG_LEVEL": "INFO",
        "LOG_FORMAT": "%(asctime)s [%(name)s] %(levelname)s: %(message)s",

        # Memory management
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_LIMIT_MB": 512,
        "MEMUSAGE_WARNING_MB": 256,

        # AutoThrottle for polite crawling
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 1,
        "AUTOTHROTTLE_MAX_DELAY": 10,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,

        # Telnet console (disabled for security)
        "TELNETCONSOLE_ENABLED": False,
    }

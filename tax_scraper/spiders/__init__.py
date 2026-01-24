"""
Site-specific spiders for tax content scraping.

To add a new spider:
1. Create a new file in this directory (e.g., mysite.py)
2. Create a class inheriting from BaseTaxSpider
3. Implement parse_article_list() and parse_article()
4. The spider will be auto-discovered by the registry
"""

from .simic_blog import SimicBlogSpider
from .furs import FursSpider
from .finance import FinanceSpider
from .registry import SpiderRegistry, get_spider, list_spiders

__all__ = [
    "SimicBlogSpider",
    "FursSpider",
    "FinanceSpider",
    "SpiderRegistry",
    "get_spider",
    "list_spiders",
]

# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._sitemap import Sitemap, sitemap_urls_from_robots

warnings.warn(
    "The scrapy.utils.sitemap module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "Sitemap",
    "sitemap_urls_from_robots",
]

# pragma: no file cover
import warnings

from scrapy.core._spidermw import SpiderMiddlewareManager
from scrapy.core._spidermw import _ScrapeFunc as ScrapeFunc
from scrapy.exceptions import ScrapyDeprecationWarning

warnings.warn(
    "The scrapy.core.spidermw module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ScrapeFunc",
    "SpiderMiddlewareManager",
]

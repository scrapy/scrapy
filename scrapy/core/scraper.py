# pragma: no file cover
import warnings

from scrapy.core._scraper import QueueTuple, Scraper
from scrapy.core._scraper import _Slot as Slot
from scrapy.exceptions import ScrapyDeprecationWarning

warnings.warn(
    "The scrapy.core.scraper module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "QueueTuple",
    "Scraper",
    "Slot",
]

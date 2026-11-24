# pragma: no file cover
import warnings

from scrapy._middleware import MiddlewareManager
from scrapy.exceptions import ScrapyDeprecationWarning

warnings.warn(
    "The scrapy.middleware module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "MiddlewareManager",
]

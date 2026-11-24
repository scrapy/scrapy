# pragma: no file cover
import warnings

from scrapy.core.downloader._middleware import DownloaderMiddlewareManager
from scrapy.exceptions import ScrapyDeprecationWarning

warnings.warn(
    "The scrapy.core.downloader.middleware module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "DownloaderMiddlewareManager",
]

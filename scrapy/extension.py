# pragma: no file cover
import warnings

from scrapy._extension import ExtensionManager
from scrapy.exceptions import ScrapyDeprecationWarning

warnings.warn(
    "The scrapy.extension module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ExtensionManager",
]

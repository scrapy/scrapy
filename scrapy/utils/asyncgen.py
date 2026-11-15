# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.python import _as_async_generator as as_async_generator
from scrapy.utils.python import _collect_asyncgen as collect_asyncgen

warnings.warn(
    "The scrapy.utils.asyncgen module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "as_async_generator",
    "collect_asyncgen",
]

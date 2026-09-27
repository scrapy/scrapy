# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._colorize import pformat, pprint

warnings.warn(
    "The scrapy.utils.display module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "pformat",
    "pprint",
]

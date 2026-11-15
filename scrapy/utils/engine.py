# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._engine import (
    format_engine_status,
    get_engine_status,
    print_engine_status,
)

warnings.warn(
    "The scrapy.utils.engine module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "format_engine_status",
    "get_engine_status",
    "print_engine_status",
]

# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._compression import gunzip, gzip_magic_number

warnings.warn(
    "The scrapy.utils.gz module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "gunzip",
    "gzip_magic_number",
]

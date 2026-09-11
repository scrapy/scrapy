# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._versions import get_versions

warnings.warn(
    "The scrapy.utils.versions module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "get_versions",
]

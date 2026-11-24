# pragma: no file cover
import warnings

from scrapy._addons import AddonManager
from scrapy.exceptions import ScrapyDeprecationWarning

warnings.warn(
    "The scrapy.addons module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "AddonManager",
]

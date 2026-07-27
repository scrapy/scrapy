import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._benchserver import *  # noqa: F403

warnings.warn(
    "scrapy.utils.benchserver is deprecated, use scrapy.utils._benchserver instead.",
    category=ScrapyDeprecationWarning,
    stacklevel=2,
)
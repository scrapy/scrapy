import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.asyncgen import collect_asyncgen  # noqa: F401


warnings.warn(
    "Module `scrapy.utils.py36` is deprecated, please import from `scrapy.utils.asyncgen` instead.",
    category=ScrapyDeprecationWarning,
    stacklevel=2,
)

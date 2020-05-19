"""
collect_asyncgen was put here but later moved to utils.asyncgen.
"""

import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.asyncgen import collect_asyncgen  # noqa: F401


warnings.warn("Module `scrapy.utils.py36` is deprecated. "
              "Please import `collect_asyncgen` from `scrapy.utils.asyncgen` instead.",
              ScrapyDeprecationWarning, stacklevel=2)

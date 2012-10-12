# This module is kept for backwards compatibility, so users can import
# scrapy.conf.settings and get the settings they expect

from scrapy.project import crawler
settings = crawler.settings

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.conf` is deprecated, use `crawler.settings` attribute instead",
    ScrapyDeprecationWarning, stacklevel=2)

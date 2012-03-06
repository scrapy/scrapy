from scrapy.project import crawler
stats = crawler.stats

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.stats` is deprecated, use `crawler.stats` attribute instead",
    ScrapyDeprecationWarning, stacklevel=2)

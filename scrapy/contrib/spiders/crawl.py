import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.spiders.crawl` is deprecated, "
              "use `scrapy.spiders.crawl` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.spiders.crawl import *

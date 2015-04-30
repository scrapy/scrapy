import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.spiders.feed` is deprecated, "
              "use `scrapy.spiders.feed` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.spiders.feed import *

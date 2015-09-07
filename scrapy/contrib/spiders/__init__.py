import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.spiders` is deprecated, "
              "use `scrapy.spiders` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.spiders import *

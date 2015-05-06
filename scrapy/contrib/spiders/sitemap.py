import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.spiders.sitemap` is deprecated, "
              "use `scrapy.spiders.sitemap` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.spiders.sitemap import *

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.httpcache` is deprecated, "
              "use `scrapy.extensions.httpcache` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions.httpcache import *

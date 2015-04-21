import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.downloadermiddleware.retry` is deprecated, "
              "use `scrapy.downloadermiddlewares.retry` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.downloadermiddlewares.retry import *

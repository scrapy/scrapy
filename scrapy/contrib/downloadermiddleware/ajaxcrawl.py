import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.downloadermiddleware.ajaxcrawl` is deprecated, "
              "use `scrapy.downloadermiddlewares.ajaxcrawl` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.downloadermiddlewares.ajaxcrawl import *

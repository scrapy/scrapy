import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.spidermiddleware.referer` is deprecated, "
              "use `scrapy.spidermiddlewares.referer` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.spidermiddlewares.referer import *

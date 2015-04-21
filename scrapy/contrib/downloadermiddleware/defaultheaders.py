import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.downloadermiddleware.defaultheaders` is deprecated, "
              "use `scrapy.downloadermiddlewares.defaultheaders` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.downloadermiddlewares.defaultheaders import *

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.downloadermiddleware.httpproxy` is deprecated, "
              "use `scrapy.downloadermiddlewares.httpproxy` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.downloadermiddlewares.httpproxy import *

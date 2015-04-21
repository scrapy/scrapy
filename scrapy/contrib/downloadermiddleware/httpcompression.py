import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.downloadermiddleware.httpcompression` is deprecated, "
              "use `scrapy.downloadermiddlewares.httpcompression` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.downloadermiddlewares.httpcompression import *

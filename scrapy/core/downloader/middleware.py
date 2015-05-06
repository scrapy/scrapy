import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.core.downloader.middleware` is deprecated, "
              "use `scrapy.downloadermiddlewares` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.downloadermiddlewares import *

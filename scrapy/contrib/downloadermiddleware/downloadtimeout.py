import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.downloadermiddleware.downloadtimeout` is deprecated, "
              "use `scrapy.downloadermiddlewares.downloadtimeout` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.downloadermiddlewares.downloadtimeout import *

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.downloadermiddleware.cookies` is deprecated, "
              "use `scrapy.downloadermiddlewares.cookies` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.downloadermiddlewares.cookies import *

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.downloadermiddleware.robotstxt` is deprecated, "
              "use `scrapy.downloadermiddlewares.robotstxt` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.downloadermiddlewares.robotstxt import *

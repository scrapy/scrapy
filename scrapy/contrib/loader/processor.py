import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.loader.processor` is deprecated, "
              "use `scrapy.loader.processor` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.loader.processor import *

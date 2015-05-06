import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.core.spidermw` is deprecated, "
              "use `scrapy.spidermiddlewares` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.spidermiddlewares import *

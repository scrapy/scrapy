import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.spidermiddleware.urllength` is deprecated, "
              "use `scrapy.spidermiddlewares.urllength` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.spidermiddlewares.urllength import *

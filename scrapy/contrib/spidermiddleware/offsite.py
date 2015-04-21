import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.spidermiddleware.offsite` is deprecated, "
              "use `scrapy.spidermiddlewares.offsite` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.spidermiddlewares.offsite import *

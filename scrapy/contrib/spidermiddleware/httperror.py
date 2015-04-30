import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.spidermiddleware.httperror` is deprecated, "
              "use `scrapy.spidermiddlewares.httperror` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.spidermiddlewares.httperror import *

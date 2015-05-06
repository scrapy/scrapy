import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.spidermiddleware.depth` is deprecated, "
              "use `scrapy.spidermiddlewares.depth` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.spidermiddlewares.depth import *

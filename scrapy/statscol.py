import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.statscol` is deprecated, "
              "use `scrapy.statscollectors` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.statscollectors import *

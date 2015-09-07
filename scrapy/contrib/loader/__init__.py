import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.loader` is deprecated, "
              "use `scrapy.loader` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.loader import *

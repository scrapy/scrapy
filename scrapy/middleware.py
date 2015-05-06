import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.middleware` is deprecated, "
              "use `scrapy.middlewaremanager` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.middlewaremanager import *

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.spiderstate` is deprecated, "
              "use `scrapy.extensions.spiderstate` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions.spiderstate import *

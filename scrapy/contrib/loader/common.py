import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.loader.common` is deprecated, "
              "use `scrapy.loader.common` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.loader.common import *

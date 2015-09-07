import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.spiders.init` is deprecated, "
              "use `scrapy.spiders.init` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.spiders.init import *

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.debug` is deprecated, "
              "use `scrapy.extensions.debug` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions.debug import *

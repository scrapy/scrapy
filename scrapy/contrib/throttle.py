import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.throttle` is deprecated, "
              "use `scrapy.extensions.throttle` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions.throttle import *

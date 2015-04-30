import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.corestats` is deprecated, "
              "use `scrapy.extensions.corestats` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions.corestats import *

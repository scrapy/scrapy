import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.feedexport` is deprecated, "
              "use `scrapy.extensions.feedexport` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions.feedexport import *

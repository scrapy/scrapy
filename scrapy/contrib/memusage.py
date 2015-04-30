import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.memusage` is deprecated, "
              "use `scrapy.extensions.memusage` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions.memusage import *

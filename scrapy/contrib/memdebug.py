import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.memdebug` is deprecated, "
              "use `scrapy.extensions.memdebug` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions.memdebug import *

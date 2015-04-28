import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.extension` is deprecated, "
              "use `scrapy.extensions` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions import *

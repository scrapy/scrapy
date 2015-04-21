import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.closespider` is deprecated, "
              "use `scrapy.extensions.closespider` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions.closespider import *

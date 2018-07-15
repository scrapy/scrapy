import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.telnet` is deprecated, "
              "use `scrapy.extensions.telnet` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions.telnet import *

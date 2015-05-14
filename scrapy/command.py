import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.command` is deprecated, "
              "use `scrapy.commands` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.commands import *

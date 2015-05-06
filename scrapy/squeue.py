import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.squeue` is deprecated, "
              "use `scrapy.squeues` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.squeues import *

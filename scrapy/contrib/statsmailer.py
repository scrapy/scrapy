import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.statsmailer` is deprecated, "
              "use `scrapy.extensions.statsmailer` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions.statsmailer import *

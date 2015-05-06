import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.linkextractors` is deprecated, "
              "use `scrapy.linkextractors` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.linkextractors import *

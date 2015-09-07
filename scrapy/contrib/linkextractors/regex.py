import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.linkextractors.regex` is deprecated, "
              "use `scrapy.linkextractors.regex` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.linkextractors.regex import *

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.linkextractors.htmlparser` is deprecated, "
              "use `scrapy.linkextractors.htmlparser` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.linkextractors.htmlparser import *

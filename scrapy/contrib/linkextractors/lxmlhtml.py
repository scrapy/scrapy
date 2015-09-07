import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.linkextractors.lxmlhtml` is deprecated, "
              "use `scrapy.linkextractors.lxmlhtml` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.linkextractors.lxmlhtml import *

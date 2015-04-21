import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.linkextractors.sgml` is deprecated, "
              "use `scrapy.linkextractors.sgml` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.linkextractors.sgml import *

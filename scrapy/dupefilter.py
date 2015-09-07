import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.dupefilter` is deprecated, "
              "use `scrapy.dupefilters` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.dupefilters import *

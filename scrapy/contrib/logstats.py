import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.logstats` is deprecated, "
              "use `scrapy.extensions.logstats` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.extensions.logstats import *

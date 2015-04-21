import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.pipeline` is deprecated, "
              "use `scrapy.pipelines` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.pipelines import *

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.pipeline.images` is deprecated, "
              "use `scrapy.pipelines.images` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.pipelines.images import *

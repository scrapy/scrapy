import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.pipeline.media` is deprecated, "
              "use `scrapy.pipelines.media` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.pipelines.media import *

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.utils.decorator` is deprecated, "
              "use `scrapy.utils.decorators` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.utils.decorators import *

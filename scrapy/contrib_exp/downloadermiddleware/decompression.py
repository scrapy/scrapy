import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib_exp.downloadermiddleware.decompression` is deprecated, "
              "use `scrapy.contrib.downloadermiddleware.decompression` instead",
    ScrapyDeprecationWarning, stacklevel=2)

from scrapy.contrib.downloadermiddleware.decompression import DecompressionMiddleware

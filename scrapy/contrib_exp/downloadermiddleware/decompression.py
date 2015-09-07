import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib_exp.downloadermiddleware.decompression` is deprecated, "
              "use `scrapy.downloadermiddlewares.decompression` instead",
    ScrapyDeprecationWarning, stacklevel=2)

from scrapy.downloadermiddlewares.decompression import DecompressionMiddleware

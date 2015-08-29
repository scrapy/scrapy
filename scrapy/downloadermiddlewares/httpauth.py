import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.downloadermiddleware.httpauth` is deprecated, "
              "use `scrapy.downloadermiddlewares.auth` instead",
              ScrapyDeprecationWarning)

from scrapy.downloadermiddlewares.auth import AuthMiddleware as HttpAuthMiddleware

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.downloadermiddleware.httpauth` is deprecated, "
              "use `scrapy.downloadermiddlewares.auth` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.utils.deprecate import create_deprecated_class
from scrapy.downloadermiddlewares.auth import AuthMiddleware

HttpAuthMiddleware = create_deprecated_class('HttpAuthMiddleware', AuthMiddleware)

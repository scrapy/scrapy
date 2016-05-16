import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.downloadermiddleware.httpauth` is deprecated, "
              "use `scrapy.downloadermiddlewares.auth` instead",
              ScrapyDeprecationWarning)

from scrapy.utils.deprecate import create_deprecated_class
from scrapy.downloadermiddlewares.auth import AuthMiddleware

HttpAuthMiddleware = create_deprecated_class('HttpAuthMiddleware', AuthMiddleware)

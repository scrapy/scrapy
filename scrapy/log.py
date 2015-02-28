"""
This module is kept to provide a helpful warning about its removal.
"""

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.log` has been deprecated, Scrapy now relies on "
              "the builtin Python library for logging. Read the updated "
              "logging entry in the documentation to learn more.",
              ScrapyDeprecationWarning, stacklevel=2)

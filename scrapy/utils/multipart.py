"""
Transitional module for moving to the w3lib library.

For new code, always import from w3lib.form instead of this module
"""
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from w3lib.form import *


warnings.warn("Module `scrapy.utils.multipart` is deprecated. "
              "If you're using `encode_multipart` function, please use "
              "`urllib3.filepost.encode_multipart_formdata` instead",
              ScrapyDeprecationWarning, stacklevel=2)
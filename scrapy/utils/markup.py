"""
Transitional module for moving to the w3lib library.

For new code, always import from w3lib.html instead of this module
"""
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from w3lib.html import *


warnings.warn("Module `scrapy.utils.markup` is deprecated. "
              "Please import from `w3lib.html` instead.",
              ScrapyDeprecationWarning, stacklevel=2)
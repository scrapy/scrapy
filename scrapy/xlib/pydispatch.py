from __future__ import absolute_import

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning

from pydispatch import (
    dispatcher,
    errors,
    robust,
    robustapply,
    saferef,
)

warnings.warn("Importing from scrapy.xlib.pydispatch is deprecated and will"
              " no longer be supported in future Scrapy versions."
              " If you just want to connect signals use the from_crawler class method,"
              " otherwise import pydispatch directly if needed."
              " See: https://github.com/scrapy/scrapy/issues/1762",
              ScrapyDeprecationWarning, stacklevel=2)

import warnings

from scrapy.exceptions import ScrapyDeprecationWarning

warnings.warn("Module `scrapy.contrib_exp.djangoitem` is deprecated, use `scrapy.contrib.djangoitem` instead",
    ScrapyDeprecationWarning, stacklevel=2)


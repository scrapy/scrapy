import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib_exp.iterators` is deprecated, use `scrapy.utils.iterators` instead",
    ScrapyDeprecationWarning, stacklevel=2)

from scrapy.utils.iterators import xmliter_lxml

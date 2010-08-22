import warnings
warnings.warn("scrapy.core.manager.scrapymanager is deprecated and will be removed in Scrapy 0.11, use scrapy.project.crawler instead", \
    DeprecationWarning, stacklevel=2)

from scrapy.project import crawler
scrapymanager = crawler

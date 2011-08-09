from scrapy.contrib.exporter import JsonLinesItemExporter
from scrapy.exceptions import ScrapyDeprecationWarning

import warnings
warnings.warn("Module `scrapy.contrib.exporter.jsonlines` is deprecated - use `scrapy.contrib.exporter` instead",
    ScrapyDeprecationWarning, stacklevel=2)

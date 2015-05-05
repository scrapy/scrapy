import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.exporter` is deprecated, "
              "use `scrapy.exporters` instead",
              ScrapyDeprecationWarning, stacklevel=2)

from scrapy.exporters import *
from scrapy.exporters import PythonItemExporter

import json
from shutil import copytree, ignore_patterns
from multiprocessing import cpu_count
from pkgutil import get_data

from scrapy.exceptions import ScrapyDeprecationWarning

import warnings
warnings.warn("Module `scrapy.utils.py26` is deprecated and will be removed in Scrapy 0.17",
    ScrapyDeprecationWarning, stacklevel=2)

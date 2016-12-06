# This module is kept for backwards compatibility, so users can import
# scrapy.conf.settings and get the settings they expect

import sys
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning

if 'scrapy.cmdline' not in sys.modules:
    from scrapy.utils.project import get_project_settings
    settings = get_project_settings()

warnings.warn("Module `scrapy.conf` is deprecated, use `crawler.settings` attribute instead",
    ScrapyDeprecationWarning, stacklevel=2)

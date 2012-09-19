# This module is kept for backwards compatibility, so users can import
# scrapy.conf.settings and get the settings they expect
#
# TODO: Add deprecation warning once all scrapy.conf instances have been
# removed from Scrapy codebase.

import sys

if 'scrapy.cmdline' not in sys.modules:
    from scrapy.utils.project import get_project_settings
    settings = get_project_settings()

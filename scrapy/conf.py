# This module is kept for backwards compatibility.
#
# TODO: Add deprecation warning once all scrapy.conf instances have been
# removed from Scrapy codebase.

from scrapy.utils.project import get_project_settings
settings = get_project_settings()

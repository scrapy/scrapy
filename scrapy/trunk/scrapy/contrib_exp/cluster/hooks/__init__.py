"""
This module contains pre-run hooks that can be attached to scrapy workers.

Pre-run hooks must be callable objects (ie. functions) which implement this
interface:

pre_hook(domain, spider_settings)

domain is the domain to be scraped
spider_settings is the settings to use to scrape it

Values returned from the pre-run hooks will be ignored.
"""

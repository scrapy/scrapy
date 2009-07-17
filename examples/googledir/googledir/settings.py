# - Scrapy settings for googledir project

import googledir

PROJECT_NAME = 'googledir'

BOT_NAME = PROJECT_NAME
BOT_VERSION = '1.0'

SPIDER_MODULES = ['googledir.spiders']
NEWSPIDER_MODULE = 'googledir.spiders'
TEMPLATES_DIR = '%s/templates' % googledir.__path__[0]
DEFAULT_ITEM_CLASS = 'scrapy.item.ScrapedItem'
USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)

ITEM_PIPELINES = ['googledir.pipelines.FilterWordsPipeline']


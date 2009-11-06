# - Scrapy settings for googledir project

import googledir

BOT_NAME = 'googledir'
BOT_VERSION = '1.0'

SPIDER_MODULES = ['googledir.spiders']
NEWSPIDER_MODULE = 'googledir.spiders'
DEFAULT_ITEM_CLASS = 'scrapy.item.Item'
USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)

ITEM_PIPELINES = ['googledir.pipelines.FilterWordsPipeline']


# Scrapy settings for googledir project
#
# For simplicity, this file contains only the most important settings by
# default. All the other settings are documented here:
#
#     http://doc.scrapy.org/topics/settings.html

BOT_NAME = 'googledir'
BOT_VERSION = '1.0'

SPIDER_MODULES = ['googledir.spiders']
NEWSPIDER_MODULE = 'googledir.spiders'
DEFAULT_ITEM_CLASS = 'googledir.items.GoogledirItem'
USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)

ITEM_PIPELINES = ['googledir.pipelines.FilterWordsPipeline']

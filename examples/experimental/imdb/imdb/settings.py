# Scrapy settings for imdb project
#
# For simplicity, this file contains only the most important settings by
# default. All the other settings are documented here:
#
#     http://doc.scrapy.org/topics/settings.html

BOT_NAME = 'imdb'
BOT_VERSION = '1.0'

SPIDER_MODULES = ['imdb.spiders']
NEWSPIDER_MODULE = 'imdb.spiders'
DEFAULT_ITEM_CLASS = 'imdb.items.ImdbItem'
USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)


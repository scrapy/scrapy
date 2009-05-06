# - Scrapy settings for googledir                                    -

import googledir

PROJECT_NAME = 'googledir'

BOT_NAME = PROJECT_NAME
BOT_VERSION = '1.0'

SPIDER_MODULES = ['googledir.spiders']
NEWSPIDER_MODULE = 'googledir.spiders'
TEMPLATES_DIR = '%s/templates' % googledir.__path__[0]
DEFAULT_ITEM_CLASS = 'scrapy.item.ScrapedItem'
USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)

# uncomment if you want to add your own custom scrapy commands
#COMMANDS_MODULE = 'googledir.commands'
#COMMANDS_SETTINGS_MODULE = 'googledir.conf.commands'

# global mail sending settings
#MAIL_HOST = 'localhost'
#MAIL_FROM = 'scrapybot@localhost'

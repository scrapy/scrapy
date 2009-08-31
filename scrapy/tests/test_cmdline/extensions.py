"""A test extension used to check the settings loading order"""

from scrapy.conf import settings

settings.overrides['TEST1'] = "%s + %s" % (settings['TEST1'], 'loaded')

class TestExtension(object):

    def __init__(self):
        settings.overrides['TEST1'] = "%s + %s" % (settings['TEST1'], 'started')

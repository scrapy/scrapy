import unittest

import scrapy
import scrapy.addons
from scrapy.addons.builtins import make_builtin_addon
from scrapy.settings import Settings


class BuiltinAddonsTest(unittest.TestCase):

    def test_make_builtin_addon(self):
        httpcache = make_builtin_addon(
            'httpcache',
            'DOWNLOADER_MIDDLEWARES',
            'scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware',
            900,
            {'enabled': True},
        )
        self.assertEqual(httpcache.name, 'httpcache')
        self.assertEqual(httpcache.component_type, 'DOWNLOADER_MIDDLEWARES')
        self.assertEqual(httpcache.component, 'scrapy.downloadermiddlewares.'
                                              'httpcache.HttpCacheMiddleware')
        self.assertEqual(httpcache.component_order, 900)
        self.assertEqual(httpcache.default_config, {'enabled': True})
        self.assertEqual(httpcache.version, scrapy.__version__)
        httpcache = make_builtin_addon(
            'httpcache',
            'DOWNLOADER_MIDDLEWARES',
            'scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware',
            900,
            {'enabled': True},
            '99.9',
        )
        self.assertEqual(httpcache.version, '99.9')

    def test_defaultheaders_export_config(self):
        settings = Settings()
        dh = scrapy.addons.defaultheaders()
        dh.export_config({'X-Test-Header': 'val'}, settings)
        self.assertIn('X-Test-Header', settings['DEFAULT_REQUEST_HEADERS'])
        self.assertEqual(settings['DEFAULT_REQUEST_HEADERS']['X-Test-Header'],
                         'val')

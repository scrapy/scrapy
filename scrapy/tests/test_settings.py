import unittest

from scrapy.settings import Settings
from scrapy.utils.test import get_crawler
from scrapy.spider import BaseSpider

class SettingsTest(unittest.TestCase):

    def test_get(self):
        settings = Settings({
            'TEST_ENABLED1': '1',
            'TEST_ENABLED2': True,
            'TEST_ENABLED3': 1,
            'TEST_DISABLED1': '0',
            'TEST_DISABLED2': False,
            'TEST_DISABLED3': 0,
            'TEST_INT1': 123,
            'TEST_INT2': '123',
            'TEST_FLOAT1': 123.45,
            'TEST_FLOAT2': '123.45',
            'TEST_LIST1': ['one', 'two'],
            'TEST_LIST2': 'one,two',
            'TEST_STR': 'value',
            'TEST_DICT1': {'key1': 'val1', 'ke2': 3},
            'TEST_DICT2': '{"key1": "val1", "ke2": 3}',
        })
        assert settings.getbool('TEST_ENABLED1') is True
        assert settings.getbool('TEST_ENABLED2') is True
        assert settings.getbool('TEST_ENABLED3') is True
        assert settings.getbool('TEST_ENABLEDx') is False
        assert settings.getbool('TEST_ENABLEDx', True) is True
        assert settings.getbool('TEST_DISABLED1') is False
        assert settings.getbool('TEST_DISABLED2') is False
        assert settings.getbool('TEST_DISABLED3') is False
        self.assertEqual(settings.getint('TEST_INT1'), 123)
        self.assertEqual(settings.getint('TEST_INT2'), 123)
        self.assertEqual(settings.getint('TEST_INTx'), 0)
        self.assertEqual(settings.getint('TEST_INTx', 45), 45)
        self.assertEqual(settings.getfloat('TEST_FLOAT1'), 123.45)
        self.assertEqual(settings.getfloat('TEST_FLOAT2'), 123.45)
        self.assertEqual(settings.getfloat('TEST_FLOATx'), 0.0)
        self.assertEqual(settings.getfloat('TEST_FLOATx', 55.0), 55.0)
        self.assertEqual(settings.getlist('TEST_LIST1'), ['one', 'two'])
        self.assertEqual(settings.getlist('TEST_LIST2'), ['one', 'two'])
        self.assertEqual(settings.getlist('TEST_LISTx'), [])
        self.assertEqual(settings.getlist('TEST_LISTx', ['default']), ['default'])
        self.assertEqual(settings['TEST_STR'], 'value')
        self.assertEqual(settings.get('TEST_STR'), 'value')
        self.assertEqual(settings['TEST_STRx'], None)
        self.assertEqual(settings.get('TEST_STRx'), None)
        self.assertEqual(settings.get('TEST_STRx', 'default'), 'default')
        self.assertEqual(settings.getdict('TEST_DICT1'), {'key1': 'val1', 'ke2': 3})
        self.assertEqual(settings.getdict('TEST_DICT2'), {'key1': 'val1', 'ke2': 3})
        self.assertEqual(settings.getdict('TEST_DICT3'), {})
        self.assertEqual(settings.getdict('TEST_DICT3', {'key1': 5}), {'key1': 5})
        self.assertRaises(ValueError, settings.getdict, 'TEST_LIST1')


class CrawlerSettingsTest(unittest.TestCase):

    def test_global_defaults(self):
        crawler = get_crawler()
        self.assertEqual(crawler.settings.getint('DOWNLOAD_TIMEOUT'), 180)

    def test_defaults(self):
        crawler = get_crawler()
        crawler.settings.defaults['DOWNLOAD_TIMEOUT'] = '99'
        self.assertEqual(crawler.settings.getint('DOWNLOAD_TIMEOUT'), 99)

    def test_settings_module(self):
        crawler = get_crawler({'DOWNLOAD_TIMEOUT': '3'})
        self.assertEqual(crawler.settings.getint('DOWNLOAD_TIMEOUT'), 3)

    def test_overrides(self):
        crawler = get_crawler({'DOWNLOAD_TIMEOUT': '3'})
        crawler.settings.overrides['DOWNLOAD_TIMEOUT'] = '15'
        self.assertEqual(crawler.settings.getint('DOWNLOAD_TIMEOUT'), 15)


if __name__ == "__main__":
    unittest.main()


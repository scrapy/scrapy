import six
import unittest
import warnings
try:
    from unittest import mock
except ImportError:
    import mock

from scrapy.settings import Settings, SettingsAttribute, CrawlerSettings
from . import default_settings


class SettingsAttributeTest(unittest.TestCase):

    def setUp(self):
        self.attribute = SettingsAttribute('value', 10)

    def test_set_greater_priority(self):
        self.attribute.set('value2', 20)
        self.assertEqual(self.attribute.value, 'value2')
        self.assertEqual(self.attribute.priority, 20)

    def test_set_equal_priority(self):
        self.attribute.set('value2', 10)
        self.assertEqual(self.attribute.value, 'value2')
        self.assertEqual(self.attribute.priority, 10)

    def test_set_less_priority(self):
        self.attribute.set('value2', 0)
        self.assertEqual(self.attribute.value, 'value')
        self.assertEqual(self.attribute.priority, 10)


class SettingsTest(unittest.TestCase):

    def setUp(self):
        self.settings = Settings()

    @mock.patch.dict('scrapy.settings.SETTINGS_PRIORITIES', {'default': 10})
    @mock.patch('scrapy.settings.default_settings', default_settings)
    def test_initial_defaults(self):
        settings = Settings()
        self.assertEqual(len(settings.attributes), 1)
        self.assertIn('TEST_DEFAULT', settings.attributes)

        attr = settings.attributes['TEST_DEFAULT']
        self.assertIsInstance(attr, SettingsAttribute)
        self.assertEqual(attr.value, 'defvalue')
        self.assertEqual(attr.priority, 10)

    @mock.patch.dict('scrapy.settings.SETTINGS_PRIORITIES', {})
    @mock.patch('scrapy.settings.default_settings', {})
    def test_initial_values(self):
        settings = Settings({'TEST_OPTION': 'value'}, 10)
        self.assertEqual(len(settings.attributes), 1)
        self.assertIn('TEST_OPTION', settings.attributes)

        attr = settings.attributes['TEST_OPTION']
        self.assertIsInstance(attr, SettingsAttribute)
        self.assertEqual(attr.value, 'value')
        self.assertEqual(attr.priority, 10)

    def test_set_new_attribute(self):
        self.settings.attributes = {}
        self.settings.set('TEST_OPTION', 'value', 0)
        self.assertIn('TEST_OPTION', self.settings.attributes)

        attr = self.settings.attributes['TEST_OPTION']
        self.assertIsInstance(attr, SettingsAttribute)
        self.assertEqual(attr.value, 'value')
        self.assertEqual(attr.priority, 0)

    def test_set_instance_identity_on_update(self):
        attr = SettingsAttribute('value', 0)
        self.settings.attributes = {'TEST_OPTION': attr}
        self.settings.set('TEST_OPTION', 'othervalue', 10)

        self.assertIn('TEST_OPTION', self.settings.attributes)
        self.assertIs(attr, self.settings.attributes['TEST_OPTION'])

    def test_set_calls_settings_attributes_methods_on_update(self):
        with mock.patch.object(SettingsAttribute, '__setattr__') as mock_setattr, \
                mock.patch.object(SettingsAttribute, 'set') as mock_set:

            attr = SettingsAttribute('value', 10)
            self.settings.attributes = {'TEST_OPTION': attr}
            mock_set.reset_mock()
            mock_setattr.reset_mock()

            for priority in (0, 10, 20):
                self.settings.set('TEST_OPTION', 'othervalue', priority)
                mock_set.assert_called_once_with('othervalue', priority)
                self.assertFalse(mock_setattr.called)
                mock_set.reset_mock()
                mock_setattr.reset_mock()

    def test_setdict_alias(self):
        with mock.patch.object(self.settings, 'set') as mock_set:
            self.settings.setdict({'TEST_1': 'value1', 'TEST_2': 'value2'}, 10)
            self.assertEqual(mock_set.call_count, 2)
            calls = [mock.call('TEST_1', 'value1', 10),
                     mock.call('TEST_2', 'value2', 10)]
            mock_set.assert_has_calls(calls, any_order=True)

    def test_setmodule_only_load_uppercase_vars(self):
        class ModuleMock():
            UPPERCASE_VAR = 'value'
            MIXEDcase_VAR = 'othervalue'
            lowercase_var = 'anothervalue'

        self.settings.attributes = {}
        self.settings.setmodule(ModuleMock(), 10)
        self.assertIn('UPPERCASE_VAR', self.settings.attributes)
        self.assertNotIn('MIXEDcase_VAR', self.settings.attributes)
        self.assertNotIn('lowercase_var', self.settings.attributes)
        self.assertEqual(len(self.settings.attributes), 1)

    def test_setmodule_alias(self):
        with mock.patch.object(self.settings, 'set') as mock_set:
            self.settings.setmodule(default_settings, 10)
            mock_set.assert_called_with('TEST_DEFAULT', 'defvalue', 10)

    def test_setmodule_by_path(self):
        self.settings.attributes = {}
        self.settings.setmodule(default_settings, 10)
        ctrl_attributes = self.settings.attributes.copy()

        self.settings.attributes = {}
        self.settings.setmodule(
            'scrapy.tests.test_settings.default_settings', 10)

        self.assertItemsEqual(six.iterkeys(self.settings.attributes),
                              six.iterkeys(ctrl_attributes))

        for attr, ctrl_attr in zip(six.itervalues(self.settings.attributes),
                                   six.itervalues(ctrl_attributes)):
            self.assertEqual(attr.value, ctrl_attr.value)
            self.assertEqual(attr.priority, ctrl_attr.priority)

    def test_get(self):
        test_configuration = {
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
        }
        settings = self.settings
        settings.attributes = {key: SettingsAttribute(value, 0) for key, value
                               in six.iteritems(test_configuration)}

        self.assertTrue(settings.getbool('TEST_ENABLED1'))
        self.assertTrue(settings.getbool('TEST_ENABLED2'))
        self.assertTrue(settings.getbool('TEST_ENABLED3'))
        self.assertFalse(settings.getbool('TEST_ENABLEDx'))
        self.assertTrue(settings.getbool('TEST_ENABLEDx', True))
        self.assertFalse(settings.getbool('TEST_DISABLED1'))
        self.assertFalse(settings.getbool('TEST_DISABLED2'))
        self.assertFalse(settings.getbool('TEST_DISABLED3'))
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

    def test_deprecated_attribute_overrides(self):
        self.settings.set('BAR', 'fuz', priority='cmdline')
        with warnings.catch_warnings(record=True) as w:
            self.settings.overrides['BAR'] = 'foo'
            self.assertIn("Settings.overrides", str(w[0].message))
            self.assertEqual(self.settings.get('BAR'), 'foo')
            self.assertEqual(self.settings.overrides.get('BAR'), 'foo')
            self.assertIn('BAR', self.settings.overrides)

            self.settings.overrides.update(BAR='bus')
            self.assertEqual(self.settings.get('BAR'), 'bus')
            self.assertEqual(self.settings.overrides.get('BAR'), 'bus')

            self.settings.overrides.setdefault('BAR', 'fez')
            self.assertEqual(self.settings.get('BAR'), 'bus')

            self.settings.overrides.setdefault('FOO', 'fez')
            self.assertEqual(self.settings.get('FOO'), 'fez')
            self.assertEqual(self.settings.overrides.get('FOO'), 'fez')


    def test_deprecated_attribute_defaults(self):
        self.settings.set('BAR', 'fuz', priority='default')
        with warnings.catch_warnings(record=True) as w:
            self.settings.defaults['BAR'] = 'foo'
            self.assertIn("Settings.defaults", str(w[0].message))
            self.assertEqual(self.settings.get('BAR'), 'foo')
            self.assertEqual(self.settings.defaults.get('BAR'), 'foo')
            self.assertIn('BAR', self.settings.defaults)


class CrawlerSettingsTest(unittest.TestCase):

    def test_deprecated_crawlersettings(self):
        def _get_settings(settings_dict=None):
            settings_module = type('SettingsModuleMock', (object,), settings_dict or {})
            return CrawlerSettings(settings_module)

        with warnings.catch_warnings(record=True) as w:
            settings = _get_settings()
            self.assertIn("CrawlerSettings is deprecated", str(w[0].message))

            # test_global_defaults
            self.assertEqual(settings.getint('DOWNLOAD_TIMEOUT'), 180)

            # test_defaults
            settings.defaults['DOWNLOAD_TIMEOUT'] = '99'
            self.assertEqual(settings.getint('DOWNLOAD_TIMEOUT'), 99)

            # test_settings_module
            settings = _get_settings({'DOWNLOAD_TIMEOUT': '3'})
            self.assertEqual(settings.getint('DOWNLOAD_TIMEOUT'), 3)

            # test_overrides
            settings = _get_settings({'DOWNLOAD_TIMEOUT': '3'})
            settings.overrides['DOWNLOAD_TIMEOUT'] = '15'
            self.assertEqual(settings.getint('DOWNLOAD_TIMEOUT'), 15)


if __name__ == "__main__":
    unittest.main()

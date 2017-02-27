import six
import unittest
import warnings

from scrapy.settings import (BaseSettings, Settings, SettingsAttribute,
                             CrawlerSettings, SETTINGS_PRIORITIES,
                             get_settings_priority)
from tests import mock
from . import default_settings


class SettingsGlobalFuncsTest(unittest.TestCase):

    def test_get_settings_priority(self):
        for prio_str, prio_num in six.iteritems(SETTINGS_PRIORITIES):
            self.assertEqual(get_settings_priority(prio_str), prio_num)
        self.assertEqual(get_settings_priority(99), 99)


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

    def test_overwrite_basesettings(self):
        original_dict = {'one': 10, 'two': 20}
        original_settings = BaseSettings(original_dict, 0)
        attribute = SettingsAttribute(original_settings, 0)

        new_dict = {'three': 11, 'four': 21}
        attribute.set(new_dict, 10)
        self.assertIsInstance(attribute.value, BaseSettings)
        six.assertCountEqual(self, attribute.value, new_dict)
        six.assertCountEqual(self, original_settings, original_dict)

        new_settings = BaseSettings({'five': 12}, 0)
        attribute.set(new_settings, 0)  # Insufficient priority
        six.assertCountEqual(self, attribute.value, new_dict)
        attribute.set(new_settings, 10)
        six.assertCountEqual(self, attribute.value, new_settings)

    def test_repr(self):
        self.assertEqual(repr(self.attribute),
                         "<SettingsAttribute value='value' priority=10>")


class BaseSettingsTest(unittest.TestCase):

    if six.PY3:
        assertItemsEqual = unittest.TestCase.assertCountEqual

    def setUp(self):
        self.settings = BaseSettings()

    def test_set_new_attribute(self):
        self.settings.set('TEST_OPTION', 'value', 0)
        self.assertIn('TEST_OPTION', self.settings.attributes)

        attr = self.settings.attributes['TEST_OPTION']
        self.assertIsInstance(attr, SettingsAttribute)
        self.assertEqual(attr.value, 'value')
        self.assertEqual(attr.priority, 0)

    def test_set_settingsattribute(self):
        myattr = SettingsAttribute(0, 30)  # Note priority 30
        self.settings.set('TEST_ATTR', myattr, 10)
        self.assertEqual(self.settings.get('TEST_ATTR'), 0)
        self.assertEqual(self.settings.getpriority('TEST_ATTR'), 30)

    def test_set_instance_identity_on_update(self):
        attr = SettingsAttribute('value', 0)
        self.settings.attributes = {'TEST_OPTION': attr}
        self.settings.set('TEST_OPTION', 'othervalue', 10)

        self.assertIn('TEST_OPTION', self.settings.attributes)
        self.assertIs(attr, self.settings.attributes['TEST_OPTION'])

    def test_set_calls_settings_attributes_methods_on_update(self):
        attr = SettingsAttribute('value', 10)
        with mock.patch.object(attr, '__setattr__') as mock_setattr, \
                mock.patch.object(attr, 'set') as mock_set:

            self.settings.attributes = {'TEST_OPTION': attr}

            for priority in (0, 10, 20):
                self.settings.set('TEST_OPTION', 'othervalue', priority)
                mock_set.assert_called_once_with('othervalue', priority)
                self.assertFalse(mock_setattr.called)
                mock_set.reset_mock()
                mock_setattr.reset_mock()

    def test_setitem(self):
        settings = BaseSettings()
        settings.set('key', 'a', 'default')
        settings['key'] = 'b'
        self.assertEqual(settings['key'], 'b')
        self.assertEqual(settings.getpriority('key'), 20)
        settings['key'] = 'c'
        self.assertEqual(settings['key'], 'c')
        settings['key2'] = 'x'
        self.assertIn('key2', settings)
        self.assertEqual(settings['key2'], 'x')
        self.assertEqual(settings.getpriority('key2'), 20)

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
            mock_set.assert_any_call('TEST_DEFAULT', 'defvalue', 10)
            mock_set.assert_any_call('TEST_DICT', {'key': 'val'}, 10)

    def test_setmodule_by_path(self):
        self.settings.attributes = {}
        self.settings.setmodule(default_settings, 10)
        ctrl_attributes = self.settings.attributes.copy()

        self.settings.attributes = {}
        self.settings.setmodule(
            'tests.test_settings.default_settings', 10)

        self.assertItemsEqual(six.iterkeys(self.settings.attributes),
                              six.iterkeys(ctrl_attributes))

        for key in six.iterkeys(ctrl_attributes):
            attr = self.settings.attributes[key]
            ctrl_attr = ctrl_attributes[key]
            self.assertEqual(attr.value, ctrl_attr.value)
            self.assertEqual(attr.priority, ctrl_attr.priority)

    def test_update(self):
        settings = BaseSettings({'key_lowprio': 0}, priority=0)
        settings.set('key_highprio', 10, priority=50)
        custom_settings = BaseSettings({'key_lowprio': 1, 'key_highprio': 11},
                                       priority=30)
        custom_settings.set('newkey_one', None, priority=50)
        custom_dict = {'key_lowprio': 2, 'key_highprio': 12, 'newkey_two': None}

        settings.update(custom_dict, priority=20)
        self.assertEqual(settings['key_lowprio'], 2)
        self.assertEqual(settings.getpriority('key_lowprio'), 20)
        self.assertEqual(settings['key_highprio'], 10)
        self.assertIn('newkey_two', settings)
        self.assertEqual(settings.getpriority('newkey_two'), 20)

        settings.update(custom_settings)
        self.assertEqual(settings['key_lowprio'], 1)
        self.assertEqual(settings.getpriority('key_lowprio'), 30)
        self.assertEqual(settings['key_highprio'], 10)
        self.assertIn('newkey_one', settings)
        self.assertEqual(settings.getpriority('newkey_one'), 50)

        settings.update({'key_lowprio': 3}, priority=20)
        self.assertEqual(settings['key_lowprio'], 1)

    def test_update_jsonstring(self):
        settings = BaseSettings({'number': 0, 'dict': BaseSettings({'key': 'val'})})
        settings.update('{"number": 1, "newnumber": 2}')
        self.assertEqual(settings['number'], 1)
        self.assertEqual(settings['newnumber'], 2)
        settings.set("dict", '{"key": "newval", "newkey": "newval2"}')
        self.assertEqual(settings['dict']['key'], "newval")
        self.assertEqual(settings['dict']['newkey'], "newval2")

    def test_delete(self):
        settings = BaseSettings({'key': None})
        settings.set('key_highprio', None, priority=50)
        settings.delete('key')
        settings.delete('key_highprio')
        self.assertNotIn('key', settings)
        self.assertIn('key_highprio', settings)
        del settings['key_highprio']
        self.assertNotIn('key_highprio', settings)

    def test_get(self):
        test_configuration = {
            'TEST_ENABLED1': '1',
            'TEST_ENABLED2': True,
            'TEST_ENABLED3': 1,
            'TEST_ENABLED4': 'True',
            'TEST_ENABLED5': 'true',
            'TEST_ENABLED_WRONG': 'on',
            'TEST_DISABLED1': '0',
            'TEST_DISABLED2': False,
            'TEST_DISABLED3': 0,
            'TEST_DISABLED4': 'False',
            'TEST_DISABLED5': 'false',
            'TEST_DISABLED_WRONG': 'off',
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
        self.assertTrue(settings.getbool('TEST_ENABLED4'))
        self.assertTrue(settings.getbool('TEST_ENABLED5'))
        self.assertFalse(settings.getbool('TEST_ENABLEDx'))
        self.assertTrue(settings.getbool('TEST_ENABLEDx', True))
        self.assertFalse(settings.getbool('TEST_DISABLED1'))
        self.assertFalse(settings.getbool('TEST_DISABLED2'))
        self.assertFalse(settings.getbool('TEST_DISABLED3'))
        self.assertFalse(settings.getbool('TEST_DISABLED4'))
        self.assertFalse(settings.getbool('TEST_DISABLED5'))
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
        self.assertRaises(ValueError, settings.getbool, 'TEST_ENABLED_WRONG')
        self.assertRaises(ValueError, settings.getbool, 'TEST_DISABLED_WRONG')

    def test_getpriority(self):
        settings = BaseSettings({'key': 'value'}, priority=99)
        self.assertEqual(settings.getpriority('key'), 99)
        self.assertEqual(settings.getpriority('nonexistentkey'), None)

    def test_getwithbase(self):
        s = BaseSettings({'TEST_BASE': BaseSettings({1: 1, 2: 2}, 'project'),
                          'TEST': BaseSettings({1: 10, 3: 30}, 'default'),
                          'HASNOBASE': BaseSettings({3: 3000}, 'default')})
        s['TEST'].set(2, 200, 'cmdline')
        six.assertCountEqual(self, s.getwithbase('TEST'),
                             {1: 1, 2: 200, 3: 30})
        six.assertCountEqual(self, s.getwithbase('HASNOBASE'), s['HASNOBASE'])
        self.assertEqual(s.getwithbase('NONEXISTENT'), {})

    def test_maxpriority(self):
        # Empty settings should return 'default'
        self.assertEqual(self.settings.maxpriority(), 0)
        self.settings.set('A', 0, 10)
        self.settings.set('B', 0, 30)
        self.assertEqual(self.settings.maxpriority(), 30)

    def test_copy(self):
        values = {
            'TEST_BOOL': True,
            'TEST_LIST': ['one', 'two'],
            'TEST_LIST_OF_LISTS': [['first_one', 'first_two'],
                                   ['second_one', 'second_two']]
        }
        self.settings.setdict(values)
        copy = self.settings.copy()
        self.settings.set('TEST_BOOL', False)
        self.assertTrue(copy.get('TEST_BOOL'))

        test_list = self.settings.get('TEST_LIST')
        test_list.append('three')
        self.assertListEqual(copy.get('TEST_LIST'), ['one', 'two'])

        test_list_of_lists = self.settings.get('TEST_LIST_OF_LISTS')
        test_list_of_lists[0].append('first_three')
        self.assertListEqual(copy.get('TEST_LIST_OF_LISTS')[0],
                             ['first_one', 'first_two'])

    def test_copy_to_dict(self):
        s = BaseSettings({'TEST_STRING': 'a string',
                          'TEST_LIST': [1, 2],
                          'TEST_BOOLEAN': False,
                          'TEST_BASE': BaseSettings({1: 1, 2: 2}, 'project'),
                          'TEST': BaseSettings({1: 10, 3: 30}, 'default'),
                          'HASNOBASE': BaseSettings({3: 3000}, 'default')})
        self.assertDictEqual(s.copy_to_dict(),
                            {'HASNOBASE': {3: 3000},
                             'TEST': {1: 10, 3: 30},
                             'TEST_BASE': {1: 1, 2: 2},
                             'TEST_BOOLEAN': False,
                             'TEST_LIST': [1, 2],
                             'TEST_STRING': 'a string'})

    def test_freeze(self):
        self.settings.freeze()
        with self.assertRaises(TypeError) as cm:
            self.settings.set('TEST_BOOL', False)
            self.assertEqual(str(cm.exception),
                             "Trying to modify an immutable Settings object")

    def test_frozencopy(self):
        frozencopy = self.settings.frozencopy()
        self.assertTrue(frozencopy.frozen)
        self.assertIsNot(frozencopy, self.settings)

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


class SettingsTest(unittest.TestCase):

    if six.PY3:
        assertItemsEqual = unittest.TestCase.assertCountEqual

    def setUp(self):
        self.settings = Settings()

    @mock.patch.dict('scrapy.settings.SETTINGS_PRIORITIES', {'default': 10})
    @mock.patch('scrapy.settings.default_settings', default_settings)
    def test_initial_defaults(self):
        settings = Settings()
        self.assertEqual(len(settings.attributes), 2)
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

    @mock.patch('scrapy.settings.default_settings', default_settings)
    def test_autopromote_dicts(self):
        settings = Settings()
        mydict = settings.get('TEST_DICT')
        self.assertIsInstance(mydict, BaseSettings)
        self.assertIn('key', mydict)
        self.assertEqual(mydict['key'], 'val')
        self.assertEqual(mydict.getpriority('key'), 0)

    @mock.patch('scrapy.settings.default_settings', default_settings)
    def test_getdict_autodegrade_basesettings(self):
        settings = Settings()
        mydict = settings.getdict('TEST_DICT')
        self.assertIsInstance(mydict, dict)
        self.assertEqual(len(mydict), 1)
        self.assertIn('key', mydict)
        self.assertEqual(mydict['key'], 'val')


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

from collections import OrderedDict
import itertools
import os.path
import six
from tests import mock
import unittest
import warnings

from pkg_resources import VersionConflict
import zope.interface
from zope.interface.verify import verifyObject
from zope.interface.exceptions import BrokenImplementation

from scrapy.addons import Addon, AddonManager
from scrapy.crawler import Crawler
from scrapy.interfaces import IAddon
from scrapy.settings import BaseSettings

from . import addons
from . import addonmod


class AddonTest(unittest.TestCase):

    def setUp(self):
        self.rawaddon = Addon()

        class AddonWithAttributes(Addon):
            name = 'Test'
            version = '1.0'
        self.testaddon = AddonWithAttributes()

    def test_interface(self):
        # Raw Addon should fail exactly b/c name and version are not given
        self.assertFalse(hasattr(self.rawaddon, 'name'))
        self.assertFalse(hasattr(self.rawaddon, 'version'))
        self.assertRaises(BrokenImplementation, verifyObject, IAddon,
                          self.rawaddon)
        verifyObject(IAddon, self.testaddon)

    def test_export_component(self):
        settings = BaseSettings({'ITEM_PIPELINES': BaseSettings(),
                                 'DOWNLOAD_HANDLERS': BaseSettings()},
                                'default')
        self.testaddon.component_type = None
        self.testaddon.export_component({}, settings)
        self.assertEqual(len(settings['ITEM_PIPELINES']), 0)
        self.testaddon.component_type = 'ITEM_PIPELINES'
        self.testaddon.component = 'test.component'
        self.testaddon.export_component({}, settings)
        six.assertCountEqual(self, settings['ITEM_PIPELINES'],
                             ['test.component'])
        self.assertEqual(settings['ITEM_PIPELINES']['test.component'], 0)
        self.testaddon.component_order = 313
        self.testaddon.export_component({}, settings)
        self.assertEqual(settings['ITEM_PIPELINES']['test.component'], 313)
        self.testaddon.component_type = 'DOWNLOAD_HANDLERS'
        self.testaddon.component_key = 'http'
        self.testaddon.export_component({}, settings)
        self.assertEqual(settings['DOWNLOAD_HANDLERS']['http'],
                         'test.component')

    def test_export_basics(self):
        settings = BaseSettings()
        self.testaddon.basic_settings = {'TESTKEY': 313, 'OTHERKEY': True}
        self.testaddon.export_basics(settings)
        self.assertEqual(settings['TESTKEY'], 313)
        self.assertEqual(settings['OTHERKEY'], True)
        self.assertEqual(settings.getpriority('TESTKEY'), 15)

    def test_export_config(self):
        settings = BaseSettings()
        self.testaddon.settings_prefix = None
        self.testaddon.config_mapping = {'MAPPED_key': 'MAPPING_WORKED'}
        self.testaddon.default_config = {'key': 55, 'defaultkey': 100}
        self.testaddon.export_config({'key': 313, 'OTHERKEY': True,
                                     'mapped_KEY': 99}, settings)
        self.assertEqual(settings['TEST_KEY'], 313)
        self.assertEqual(settings['TEST_DEFAULTKEY'], 100)
        self.assertEqual(settings['TEST_OTHERKEY'], True)
        self.assertNotIn('MAPPED_key', settings)
        self.assertNotIn('MAPPED_KEY', settings)
        self.assertEqual(settings['MAPPING_WORKED'], 99)
        self.assertEqual(settings.getpriority('TEST_KEY'), 15)

        self.testaddon.settings_prefix = 'PREF'
        self.testaddon.export_config({'newkey': 99}, settings)
        self.assertEqual(settings['PREF_NEWKEY'], 99)

        with mock.patch.object(settings, 'set') as mock_set:
            self.testaddon.settings_prefix = False
            self.testaddon.export_config({'thirdnewkey': 99}, settings)
            self.assertEqual(mock_set.call_count, 0)

    def test_update_settings(self):
        settings = BaseSettings()
        settings.set('TEST_KEY1', 'default', priority='default')
        settings.set('TEST_KEY2', 'project', priority='project')
        self.testaddon.settings_prefix = None
        self.testaddon.basic_settings = {'OTHERTEST_KEY': 'addon'}
        addon_config = {'key1': 'addon', 'key2': 'addon', 'key3': 'addon'}
        self.testaddon.update_settings(addon_config, settings)
        self.assertEqual(settings['OTHERTEST_KEY'], 'addon')
        self.assertEqual(settings['TEST_KEY1'], 'addon')
        self.assertEqual(settings['TEST_KEY2'], 'project')
        self.assertEqual(settings['TEST_KEY3'], 'addon')


class AddonManagerTest(unittest.TestCase):

    ADDONMODPATH = os.path.join(os.path.dirname(__file__), 'addonmod.py')

    def setUp(self):
        self.manager = AddonManager()

    def test_add(self):
        manager = AddonManager()
        manager.add(addonmod, {'key': 'val1'})
        manager.add('tests.test_addons.addons.GoodAddon')
        six.assertCountEqual(self, manager, ['AddonModule', 'GoodAddon'])
        self.assertIsInstance(manager['GoodAddon'], addons.GoodAddon)
        six.assertCountEqual(self, manager.configs['AddonModule'], ['key'])
        self.assertEqual(manager.configs['AddonModule']['key'], 'val1')
        self.assertRaises(ValueError, manager.add, addonmod)

    def test_add_dont_instantiate_providing_classes(self):
        class ProviderGoodAddon(addons.GoodAddon):
            pass
        zope.interface.directlyProvides(ProviderGoodAddon, IAddon)
        manager = AddonManager()
        manager.add(ProviderGoodAddon)
        self.assertIs(manager['GoodAddon'], ProviderGoodAddon)

    def test_add_verifies(self):
        brokenaddon = self.manager.get_addon(
            'tests.test_addons.addons.BrokenAddon')
        self.assertRaises(zope.interface.exceptions.BrokenImplementation,
                          self.manager.add,
                          brokenaddon)

    def test_add_adds_missing_interface_declaration(self):
        class GoodAddonWithoutDeclaration(object):
            name = 'GoodAddonWithoutDeclaration'
            version = '1.0'
        self.manager.add(GoodAddonWithoutDeclaration)

    def test_remove(self):
        manager = AddonManager()

        def test_gets_removed(removearg):
            manager.add(addonmod)
            self.assertIn('AddonModule', manager)
            manager.remove(removearg)
            self.assertNotIn('AddonModule', manager)

        test_gets_removed('AddonModule')
        test_gets_removed(addonmod)
        test_gets_removed('tests.test_addons.addonmod')
        test_gets_removed(self.ADDONMODPATH)
        self.assertRaises(KeyError, manager.remove, 'nonexistent')
        self.assertRaises(KeyError, manager.remove, addons.GoodAddon())

    def test_get_addon(self):
        goodaddon = self.manager.get_addon('tests.test_addons.addons.GoodAddon')
        self.assertIs(goodaddon, addons.GoodAddon)

        loaded_addonmod = self.manager.get_addon(self.ADDONMODPATH)
        # XXX: The module is in fact imported twice under different names into
        #      sys.modules, is there a good assertion for module equality?
        self.assertEqual(loaded_addonmod.name, addonmod.name)

        # Does not provide interface, but has _addon attribute pointing to
        # GoodAddon instance
        addonspath = os.path.join(os.path.dirname(__file__), 'addons.py')
        goodaddon = self.manager.get_addon(addonspath)
        # XXX: Again, the imported class and addons.GoodAddon are different
        #      since they are imported twice. How to use isInstance?
        self.assertEqual(goodaddon.name, addons.GoodAddon.name)

        self.assertRaises(NameError, self.manager.get_addon, 'xy.n_onexistent')

    def test_get_addon_forward(self):
        class SomeCls(object):
            _addon = 'tests.test_addons.addons.GoodAddon'
        self.assertIs(self.manager.get_addon(SomeCls()), addons.GoodAddon)

    def test_get_addon_nested(self):
        x = addons.GoodAddon('outer')
        x._addon = addons.GoodAddon('middle')
        x._addon._addon = addons.GoodAddon('inner')
        self.assertIs(self.manager.get_addon(x), x._addon._addon)

    def test_load_dict_load_settings(self):
        def _test_load_method(func, *args, **kwargs):
            manager = AddonManager()
            getattr(manager, func)(*args, **kwargs)
            six.assertCountEqual(self, manager, ['GoodAddon', 'AddonModule'])
            self.assertIsInstance(manager['GoodAddon'], addons.GoodAddon)
            six.assertCountEqual(self, manager.configs['GoodAddon'], ['key'])
            self.assertEqual(manager.configs['GoodAddon']['key'], 'val2')
            # XXX: Check module equality, see above
            self.assertEqual(manager['AddonModule'].name, addonmod.name)
            self.assertIn('key', manager.configs['AddonModule'])
            self.assertEqual(manager.configs['AddonModule']['key'], 'val1')

        addonsdict = {
            self.ADDONMODPATH: {
                'key': 'val1',
                },
            'tests.test_addons.addons.GoodAddon': {'key': 'val2'},
            }
        _test_load_method('load_dict', addonsdict)

        settings = BaseSettings()
        settings.set('ADDONS', {self.ADDONMODPATH: 0,
                                'tests.test_addons.addons.GoodAddon': 0})
        settings.set('ADDONMODULE', {'key': 'val1'})
        settings.set('GOODADDON', {'key': 'val2'})
        _test_load_method('load_settings', settings)

    def test_load_dict_load_settings_order(self):
        def _test_load_method(expected_order, func, *args, **kwargs):
            manager = AddonManager()
            getattr(manager, func)(*args, **kwargs)
            self.assertEqual(list(manager.keys()), expected_order)

        # Get three addons named 0, 1, 2
        addonlist = [addons.GoodAddon(str(x)) for x in range(3)]
        # Test both methods for every possible mutation
        for ordered_addons in itertools.permutations(addonlist):
            expected_order = [a.name for a in ordered_addons]
            addonsdict = OrderedDict((a, {}) for a in ordered_addons)
            _test_load_method(expected_order, 'load_dict', addonsdict)
            settings = BaseSettings({
                'ADDONS': {a: i for i, a in enumerate(ordered_addons)}
            })
            _test_load_method(expected_order, 'load_settings', settings)

    def test_enabled_disabled(self):
        manager = AddonManager()
        manager.add(addons.GoodAddon('FirstAddon'))
        manager.add(addons.GoodAddon('SecondAddon'))
        self.assertEqual(set(manager.enabled),
                         set(('FirstAddon', 'SecondAddon')))
        self.assertEqual(manager.disabled, [])
        manager.disable('FirstAddon')
        self.assertEqual(manager.enabled, ['SecondAddon'])
        self.assertEqual(manager.disabled, ['FirstAddon'])
        manager.enable('FirstAddon')
        self.assertEqual(set(manager.enabled),
                         set(('FirstAddon', 'SecondAddon')))
        self.assertEqual(manager.disabled, [])

    def test_enable_before_add(self):
        manager = AddonManager()
        self.assertRaises(ValueError, manager.enable, 'FirstAddon')
        manager.disable('FirstAddon')
        manager.enable('FirstAddon')
        manager.add(addons.GoodAddon('FirstAddon'))
        self.assertIn('FirstAddon', manager.enabled)

    def test_disable_before_add(self):
        manager = AddonManager()
        manager.disable('FirstAddon')
        manager.add(addons.GoodAddon('FirstAddon'))
        self.assertEqual(manager.disabled, ['FirstAddon'])

    def test_callbacks(self):
        first_addon = addons.GoodAddon('FirstAddon')
        second_addon = addons.GoodAddon('SecondAddon')

        manager = AddonManager()
        manager.add(first_addon, {'test': 'first'})
        manager.add(second_addon, {'test': 'second'})
        crawler = mock.create_autospec(Crawler)
        settings = BaseSettings()

        with mock.patch.object(first_addon, 'update_addons') as ua_first, \
             mock.patch.object(second_addon, 'update_addons') as ua_second, \
             mock.patch.object(first_addon, 'update_settings') as us_first, \
             mock.patch.object(second_addon, 'update_settings') as us_second, \
             mock.patch.object(first_addon, 'check_configuration') as cc_first, \
             mock.patch.object(second_addon, 'check_configuration') as cc_second:
            manager.update_addons()
            ua_first.assert_called_once_with(manager.configs['FirstAddon'],
                                             manager)
            ua_second.assert_called_once_with(manager.configs['SecondAddon'],
                                              manager)
            manager.update_settings(settings)
            us_first.assert_called_once_with(manager.configs['FirstAddon'],
                                             settings)
            us_second.assert_called_once_with(manager.configs['SecondAddon'],
                                              settings)
            manager.check_configuration(crawler)
            cc_first.assert_called_once_with(manager.configs['FirstAddon'],
                                             crawler)
            cc_second.assert_called_once_with(manager.configs['SecondAddon'],
                                              crawler)
            self.assertEqual(ua_first.call_count, 1)
            self.assertEqual(ua_second.call_count, 1)
            self.assertEqual(us_first.call_count, 1)
            self.assertEqual(us_second.call_count, 1)

            us_first.reset_mock()
            us_second.reset_mock()
            manager.disable('FirstAddon')
            manager.update_settings(settings)
            self.assertEqual(us_first.call_count, 0)
            manager.enable('FirstAddon')
            manager.update_settings(settings)
            self.assertEqual(us_first.call_count, 1)
            self.assertEqual(us_second.call_count, 2)

        # This will become relevant when we let spiders implement the add-on
        # interface and should be replaced with a test where
        # AddonManager.spidercls = None then.
        manager._call_if_exists(None, 'irrelevant')

    def test_update_addons_last_minute_add(self):
        class AddedAddon(addons.GoodAddon):
            name = 'AddedAddon'

        class FirstAddon(addons.GoodAddon):
            name = 'FirstAddon'

            def update_addons(self, config, addons):
                addons.add(AddedAddon())

        manager = AddonManager()
        first_addon = FirstAddon()
        with mock.patch.object(first_addon, 'update_addons',
                               wraps=first_addon.update_addons) as ua_first, \
             mock.patch.object(AddedAddon, 'update_addons') as ua_added:
            manager.add(first_addon, {'non-empty': 'dict'})
            manager.update_addons()
            six.assertCountEqual(self, manager, ['FirstAddon', 'AddedAddon'])
            ua_first.assert_called_once_with(manager.configs['FirstAddon'],
                                             manager)
            ua_added.assert_called_once_with(manager.configs['AddedAddon'],
                                             manager)

    def test_check_dependency_clashes_attributes(self):
        provides = addons.GoodAddon("ProvidesAddon")
        provides.provides = ('test', )
        provides2 = addons.GoodAddon("ProvidesAddon2")
        provides2.provides = ('test', )
        requires = addons.GoodAddon("RequiresAddon")
        requires.requires = ('test', )
        requires_name = addons.GoodAddon("RequiresNameAddon")
        requires_name.requires = ('ProvidesAddon', )
        requires_newer = addons.GoodAddon("RequiresNewerAddon")
        requires_newer.requires = ('test>=2.0', )
        modifies = addons.GoodAddon("ModifiesAddon")
        modifies.modifies = ('test', )

        def check_with(*addons):
            manager = AddonManager()
            for a in addons:
                manager.add(a)
            return manager.check_dependency_clashes()

        self.assertRaises(ImportError, check_with, requires)
        self.assertRaises(ImportError, check_with, modifies)
        self.assertRaises(ImportError, check_with, provides, provides2)
        self.assertRaises(VersionConflict, check_with, provides, requires_newer)
        with warnings.catch_warnings(record=True) as w:
            check_with(provides, modifies)
            check_with(provides)
            check_with(provides, requires)
            check_with(provides, requires_name)
            self.assertEqual(len(w), 0)
            check_with(requires, provides, modifies)
            self.assertEqual(len(w), 1)

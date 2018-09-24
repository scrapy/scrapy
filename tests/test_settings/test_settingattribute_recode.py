#!/usr/bin/env python
# encoding: utf-8
"""
    @file: test_settingattribute_recode.py
    
    ~~~~~~~~~~~


    :copyright: (c) 2017 by the eigen.
    :license: BSD, see LICENSE for more details.
    @time: 2018/9/25 上午1:22
"""
# eigen modified
# pylint: disable = c0301
import unittest

import six

from scrapy.settings import BaseSettings, SettingsAttribute
from . import default_settings


class SettingsAttributeTest(unittest.TestCase):
    def test_record_for_different_priorities(self):
        attribute = SettingsAttribute('value', 10)
        attribute.set('value2', 20)
        attribute.set('value3', 10)
        self.assertEqual(attribute.record, {10: 'value3', 20: 'value2'})

    def test_record_for_basesettings_overrides(self):
        original_dict = {'one': 10, 'two': 20}
        original_settings = BaseSettings(original_dict, 0)
        attribute = SettingsAttribute(original_settings, 0)

        new_dict = {'three': 11, 'four': 21}
        attribute.set(new_dict, 10)
        six.assertCountEqual(self, attribute.record[0], {'one': 10, 'two': 20})
        six.assertCountEqual(self, attribute.record[10], {'three': 11, 'four': 21})

        new_settings = BaseSettings({'five': 12}, 0)
        attribute.set(new_settings, 0)
        six.assertCountEqual(self, attribute.record[0], {'five': 12})


class BaseSettingsTest(unittest.TestCase):
    def setUp(self):
        self.settings = BaseSettings()

    def test_set_record_for_a_new_attribute(self):
        self.settings.set('TEST_OPTION', 'value', 0)
        self.assertEqual(self.settings.get_record('TEST_OPTION'), {0: 'value'})

    def test_set_record_for_existing_attribute_with_settingsattribute_typed_value(self):
        myattr = SettingsAttribute(0, 0)  # Note priority 30
        self.settings.set('TEST_ATTR', myattr, 10)
        self.assertEqual(self.settings.get_record('TEST_ATTR'), {0: 0})

    def test_records_are_kept_for_resettings(self):
        attr = SettingsAttribute('value', 0)
        self.settings.attributes = {'TEST_OPTION': attr}
        self.settings.set('TEST_OPTION', 'othervalue', 10)
        self.assertEqual(self.settings.get_record('TEST_OPTION'), {0: 'value', 10: 'othervalue'})

    def test_records_after_update(self):
        settings = BaseSettings({'prio': 0}, priority=0)
        settings.set('prio', 10, priority=50)
        custom_settings = BaseSettings({'prio': 1}, priority=30)
        custom_settings.set('newkey_one', None, priority=50)
        custom_dict = {'prio': 2, 'newkey_two': None}

        settings.update(custom_dict, priority=20)
        self.assertEqual(settings.get_record('prio'), {50: 10, 20: 2, 0: 0})  # check records are kept by update
        self.assertEqual(settings.get_record('newkey_two'), {20: None})  # check new records added by update

    def test_recordes_after_setmodule(self):
        settings = BaseSettings()
        settings.setmodule(default_settings, 10)
        self.assertEqual(settings.get_record('TEST_DEFAULT'), {10: 'defvalue'})
        self.assertEqual(settings.get_record('TEST_DICT'), {10: {'key': 'val'}})

    def test_get_settings_of_a_given_priority(self):
        settings = BaseSettings()
        settings.setmodule(default_settings, 20)
        self.assertEqual(settings.get_priority_settings(20), {'TEST_DEFAULT': 'defvalue', 'TEST_DICT': {'key': 'val'}})

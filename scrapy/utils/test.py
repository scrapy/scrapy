"""
This module contains some assorted functions used in tests
"""

import os

from importlib import import_module
from twisted.trial.unittest import SkipTest


def assert_aws_environ():
    """Asserts the current environment is suitable for running AWS testsi.
    Raises SkipTest with the reason if it's not.
    """
    try:
        import boto
    except ImportError as e:
        raise SkipTest(str(e))

    if 'AWS_ACCESS_KEY_ID' not in os.environ:
        raise SkipTest("AWS keys not found")

def get_crawler(settings_dict=None):
    """Return an unconfigured Crawler object. If settings_dict is given, it
    will be used as the settings present in the settings module of the
    CrawlerSettings.
    """
    from scrapy.crawler import Crawler
    from scrapy.settings import CrawlerSettings

    class SettingsModuleMock(object):
        pass
    settings_module = SettingsModuleMock()
    if settings_dict:
        for k, v in settings_dict.items():
            setattr(settings_module, k, v)
    settings = CrawlerSettings(settings_module)
    return Crawler(settings)

def get_pythonpath():
    """Return a PYTHONPATH suitable to use in processes so that they find this
    installation of Scrapy"""
    scrapy_path = import_module('scrapy').__path__[0]
    return os.path.dirname(scrapy_path) + os.pathsep + os.environ.get('PYTHONPATH', '')

def get_testenv():
    """Return a OS environment dict suitable to fork processes that need to import
    this installation of Scrapy, instead of a system installed one.
    """
    env = os.environ.copy()
    env['PYTHONPATH'] = get_pythonpath()
    return env

def get_testlog():
    """Get Scrapy log of current test, ignoring the rest"""
    thistest = []
    loglines = open("test.log").readlines()
    for l in loglines[::-1]:
        thistest.append(l)
        if "[-] -->" in l:
            break
    return "".join(thistest[::-1])


def assert_samelines(testcase, text1, text2, msg=None):
    """Asserts text1 and text2 have the same lines, ignoring differences in
    line endings between platforms
    """
    testcase.assertEqual(text1.splitlines(), text2.splitlines(), msg)

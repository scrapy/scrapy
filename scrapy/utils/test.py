"""
This module contains some assorted functions used in tests
"""

import os, sys

from twisted.trial.unittest import SkipTest

def libxml2debug(testfunction):
    """Decorator for debugging libxml2 memory leaks inside a function.
    
    We've found libxml2 memory leaks are something very weird, and can happen
    sometimes depending on the order where tests are run. So this decorator
    enables libxml2 memory leaks debugging only when the environment variable
    LIBXML2_DEBUGLEAKS is set.

    """
    try:
        import libxml2
    except ImportError:
        return testfunction
    def newfunc(*args, **kwargs):
        libxml2.debugMemory(1)
        testfunction(*args, **kwargs)
        libxml2.cleanupParser()
        leaked_bytes = libxml2.debugMemory(0) 
        assert leaked_bytes == 0, "libxml2 memory leak detected: %d bytes" % leaked_bytes

    if 'LIBXML2_DEBUGLEAKS' in os.environ:
        return newfunc
    else:
        return testfunction

def assert_aws_environ():
    """Asserts the current environment is suitable for running AWS testsi.
    Raises SkipTest with the reason if it's not.
    """
    try:
        import boto
    except ImportError, e:
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
    sep = ';' if sys.platform == 'win32' else ':'
    scrapy_path = __import__('scrapy').__path__[0]
    return os.path.dirname(scrapy_path) + sep + os.environ.get('PYTHONPATH', '')

def assert_samelines(testcase, text1, text2, msg=None):
    """Asserts text1 and text2 have the same lines, ignoring differences in
    line endings between platforms
    """
    testcase.assertEqual(text1.splitlines(), text2.splitlines(), msg)

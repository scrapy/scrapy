import os
import re
from configparser import ConfigParser
from importlib import import_module

from twisted import version as twisted_version
from twisted.trial import unittest


class ScrapyUtilsTest(unittest.TestCase):

    def test_required_openssl_version(self):
        try:
            module = import_module('OpenSSL')
        except ImportError:
            raise unittest.SkipTest("OpenSSL is not available")

        if hasattr(module, '__version__'):
            installed_version = [int(x) for x in module.__version__.split('.')[:2]]
            assert installed_version >= [0, 6], "OpenSSL >= 0.6 required"

    def test_pinned_twisted_version(self):
        """When running tests within a Tox environment with pinned
        dependencies, make sure that the version of Twisted is the pinned
        version.

        See https://github.com/scrapy/scrapy/pull/4814#issuecomment-706230011
        """
        if not os.environ.get('_SCRAPY_PINNED', None):
            self.skipTest('Not in a pinned environment')

        tox_config_file_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            'tox.ini',
        )
        config_parser = ConfigParser()
        config_parser.read(tox_config_file_path)
        pattern = r'Twisted\[http2\]==([\d.]+)'
        match = re.search(pattern, config_parser['pinned']['deps'])
        pinned_twisted_version_string = match[1]

        self.assertEqual(
            twisted_version.short(),
            pinned_twisted_version_string
        )


if __name__ == "__main__":
    unittest.main()

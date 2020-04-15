from importlib import import_module
from twisted.trial import unittest


class ScrapyUtilsTest(unittest.TestCase):
    def test_required_openssl_version(self):
        try:
            module = import_module('OpenSSL')
        except ImportError as ex:
            raise unittest.SkipTest("OpenSSL is not available")

        if hasattr(module, '__version__'):
            installed_version = [int(x) for x in module.__version__.split('.')[:2]]
            assert installed_version >= [0, 6], "OpenSSL >= 0.6 required"


if __name__ == "__main__":
    unittest.main()

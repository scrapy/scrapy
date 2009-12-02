from twisted.trial import unittest

class ScrapyUtilsTest(unittest.TestCase):
    def test_required_openssl_version(self):
        try:
            module = __import__('OpenSSL', {}, {}, [''])
        except ImportError, ex:
            raise unittest.SkipTest("OpenSSL is not available")

        required_version = '0.6'
        if hasattr(module, '__version__'):
            for cur, req in zip(module.__version__.split('.'), required_version.split('.')):
                self.assertFalse(cur < req, "module %s >= %s required" % ('OpenSSL', required_version))

if __name__ == "__main__":
    unittest.main()

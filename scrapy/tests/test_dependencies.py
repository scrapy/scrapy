from unittest import TestCase, main

class ScrapyUtilsTest(TestCase):
    def test_openssl(self):
        try:
            module = __import__('OpenSSL', {}, {}, [''])
        except ImportError, ex:
            return # no openssl installed

        required_version = '0.6'
        if hasattr(module, '__version__'):
            for cur, req in zip(module.__version__.split('.'), required_version.split('.')):
                self.assertFalse(cur < req, "module %s >= %s required" % ('OpenSSL', required_version))

if __name__ == "__main__":
    main()

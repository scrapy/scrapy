import sys
from unittest import TestCase, main

class DefaultEncodingTest(TestCase):
    def test_defaultencoding(self):
        self.assertEqual(sys.getdefaultencoding(), 'utf-8')

if __name__ == "__main__":
    main()

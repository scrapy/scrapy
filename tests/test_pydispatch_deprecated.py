from importlib import reload
import unittest
import warnings


class DeprecatedPydispatchTest(unittest.TestCase):
    def test_import_xlib_pydispatch_show_warning(self):
        with warnings.catch_warnings(record=True) as w:
            from scrapy.xlib import pydispatch
            reload(pydispatch)
        self.assertIn('Importing from scrapy.xlib.pydispatch is deprecated',
                      str(w[0].message))

import sys
import unittest

class SettingsSafeModulesTest(unittest.TestCase):

    # these modules must not load scrapy.conf
    SETTINGS_SAFE_MODULES = [
        'scrapy.utils.project',
        'scrapy.utils.conf',
        'scrapyd.interfaces',
        'scrapyd.eggutils',
    ]

    def test_modules_that_shouldnt_load_settings(self):
        sys.modules.pop('scrapy.conf', None)
        for m in self.SETTINGS_SAFE_MODULES:
            __import__(m)
            assert 'scrapy.conf' not in sys.modules, \
                "Module %r must not cause the scrapy.conf module to be loaded" % m

if __name__ == "__main__":
    unittest.main()

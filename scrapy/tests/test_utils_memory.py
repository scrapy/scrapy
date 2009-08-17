import os

from twisted.trial import unittest

from scrapy.utils.memory import get_vmvalue_from_procfs

class UtilsMemoryTestCase(unittest.TestCase):

    def test_get_vmvalue_from_procfs(self):
        if not os.path.exists('/proc'):
            raise unittest.SkipTest('/proc filesystem not supported')
        vmsize = get_vmvalue_from_procfs('VmSize')
        vmrss = get_vmvalue_from_procfs('VmRSS')
        assert vmsize > 0
        assert vmrss > 0
        assert vmsize > vmrss

if __name__ == "__main__":
    unittest.main()

from twisted.trial import unittest

from scrapy.utils.memory import get_vmvalue_from_procfs, procfs_supported

class UtilsMemoryTestCase(unittest.TestCase):

    def test_get_vmvalue_from_procfs(self):
        if not procfs_supported():
            raise unittest.SkipTest('/proc filesystem not supported')
        vmsize = get_vmvalue_from_procfs('VmSize')
        vmrss = get_vmvalue_from_procfs('VmRSS')
        self.assert_(isinstance(vmsize, int))
        self.assert_(vmsize > 0)
        self.assert_(vmrss > 0)
        self.assert_(vmsize > vmrss)

if __name__ == "__main__":
    unittest.main()

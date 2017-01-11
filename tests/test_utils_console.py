import unittest

from scrapy.utils.console import get_shell_embed_func
try:
    import bpython
    bpy = True
    del bpython
except ImportError:
    bpy = False
try:
    import IPython
    ipy = True
    del IPython
except ImportError:
    ipy = False


class UtilsConsoleTestCase(unittest.TestCase):

    def test_get_shell_embed_func(self):

        shell = get_shell_embed_func(['invalid'])
        self.assertEqual(shell, None)

        shell = get_shell_embed_func(['invalid', 'python'])
        self.assertTrue(callable(shell))
        self.assertEqual(shell.__name__, '_embed_standard_shell')

    @unittest.skipIf(not bpy, 'bpython not available in testenv')
    def test_get_shell_embed_func2(self):

        shell = get_shell_embed_func(['bpython'])
        self.assertTrue(callable(shell))
        self.assertEqual(shell.__name__, '_embed_bpython_shell')

    @unittest.skipIf(not ipy, 'IPython not available in testenv')
    def test_get_shell_embed_func3(self):

        # default shell should be 'ipython'
        shell = get_shell_embed_func()
        self.assertEqual(shell.__name__, '_embed_ipython_shell')


if __name__ == "__main__":
    unittest.main()

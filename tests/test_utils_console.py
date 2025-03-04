import pytest

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


class TestUtilsConsole:
    def test_get_shell_embed_func(self):
        shell = get_shell_embed_func(["invalid"])
        assert shell is None

        shell = get_shell_embed_func(["invalid", "python"])
        assert callable(shell)
        assert shell.__name__ == "_embed_standard_shell"

    @pytest.mark.skipif(not bpy, reason="bpython not available in testenv")
    def test_get_shell_embed_func2(self):
        shell = get_shell_embed_func(["bpython"])
        assert callable(shell)
        assert shell.__name__ == "_embed_bpython_shell"

    @pytest.mark.skipif(not ipy, reason="IPython not available in testenv")
    def test_get_shell_embed_func3(self):
        # default shell should be 'ipython'
        shell = get_shell_embed_func()
        assert shell.__name__ == "_embed_ipython_shell"

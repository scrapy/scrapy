import sys
from types import ModuleType

import pytest

from scrapy.utils import console
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


def test_get_shell_embed_func():
    shell = get_shell_embed_func(["invalid"])
    assert shell is None

    shell = get_shell_embed_func(["invalid", "python"])
    assert callable(shell)
    assert shell.__name__ == "_embed_standard_shell"


@pytest.mark.skipif(not bpy, reason="bpython not available in testenv")
def test_get_shell_embed_func_bpython():
    shell = get_shell_embed_func(["bpython"])
    assert callable(shell)
    assert shell.__name__ == "_embed_bpython_shell"


@pytest.mark.skipif(not ipy, reason="IPython not available in testenv")
def test_get_shell_embed_func_ipython():
    # default shell should be 'ipython'
    shell = get_shell_embed_func()
    assert shell.__name__ == "_embed_ipython_shell"


def test_embed_ipython_shell_applies_nest_asyncio_with_asyncio_reactor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied: list[bool] = []

    class FakeInteractiveShellEmbed:
        @classmethod
        def clear_instance(cls) -> None:
            pass

        @classmethod
        def instance(cls, **kwargs):
            return lambda: None

    embed_module = ModuleType("IPython.terminal.embed")
    embed_module.InteractiveShellEmbed = FakeInteractiveShellEmbed
    ipapp_module = ModuleType("IPython.terminal.ipapp")
    ipapp_module.load_default_config = object
    nest_asyncio_module = ModuleType("nest_asyncio")
    nest_asyncio_module.apply = lambda: applied.append(True)

    monkeypatch.setitem(sys.modules, "IPython.terminal.embed", embed_module)
    monkeypatch.setitem(sys.modules, "IPython.terminal.ipapp", ipapp_module)
    monkeypatch.setitem(sys.modules, "nest_asyncio", nest_asyncio_module)
    monkeypatch.setattr(
        console, "is_asyncio_reactor_installed", lambda: True, raising=False
    )

    shell = console._embed_ipython_shell()
    shell(namespace={}, banner="")

    assert applied == [True]

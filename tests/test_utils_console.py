from __future__ import annotations

from importlib.util import find_spec

import pytest

from scrapy.utils.console import get_shell_embed_func


def test_get_shell_embed_func():
    shell = get_shell_embed_func(["invalid"])
    assert shell is None

    shell = get_shell_embed_func(["invalid", "python"])
    assert callable(shell)
    assert shell.__name__ == "_embed_standard_shell"


def test_get_shell_embed_func_python():
    # the standard shell is always available
    shell = get_shell_embed_func(["python"])
    assert callable(shell)
    assert shell.__name__ == "_embed_standard_shell"


def test_get_shell_embed_func_bpython():
    pytest.importorskip("bpython")
    shell = get_shell_embed_func(["bpython"])
    assert callable(shell)
    assert shell.__name__ == "_embed_bpython_shell"


def test_get_shell_embed_func_ipython():
    pytest.importorskip("IPython")
    shell = get_shell_embed_func(["ipython"])
    assert shell is not None
    assert shell.__name__ == "_embed_ipython_shell"


def test_get_shell_embed_func_ptpython():
    pytest.importorskip("ptpython")
    shell = get_shell_embed_func(["ptpython"])
    assert shell is not None
    assert shell.__name__ == "_embed_ptpython_shell"


def test_get_shell_embed_func_default():
    # with no shells given, the first available shell in preference order
    # (ptpython, ipython, bpython, python) is returned; the standard shell
    # is always available, so the default is never None
    shell = get_shell_embed_func()
    assert shell is not None
    if find_spec("ptpython") is not None:
        expected = "_embed_ptpython_shell"
    elif find_spec("IPython") is not None:
        expected = "_embed_ipython_shell"
    elif find_spec("bpython") is not None:
        expected = "_embed_bpython_shell"
    else:
        expected = "_embed_standard_shell"
    assert shell.__name__ == expected

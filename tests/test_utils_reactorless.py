from __future__ import annotations

import sys

import pytest

from scrapy.utils.reactorless import (
    ReactorImportHook,
    install_reactor_import_hook,
    uninstall_reactor_import_hook,
)


class TestReactorImportHook:
    def test_install_and_uninstall(self) -> None:
        hook = install_reactor_import_hook()
        try:
            assert isinstance(hook, ReactorImportHook)
            assert sys.meta_path[0] is hook
        finally:
            uninstall_reactor_import_hook(hook)
        assert hook not in sys.meta_path

    def test_uninstall_twice(self) -> None:
        hook = install_reactor_import_hook()
        uninstall_reactor_import_hook(hook)
        uninstall_reactor_import_hook(hook)
        assert hook not in sys.meta_path

    def test_uninstall_not_installed(self) -> None:
        uninstall_reactor_import_hook(ReactorImportHook())

    def test_uninstall_only_removes_the_given_hook(self) -> None:
        hook1 = install_reactor_import_hook()
        hook2 = install_reactor_import_hook()
        try:
            uninstall_reactor_import_hook(hook1)
            assert hook1 not in sys.meta_path
            assert hook2 in sys.meta_path
        finally:
            uninstall_reactor_import_hook(hook1)
            uninstall_reactor_import_hook(hook2)

    def test_find_spec(self) -> None:
        hook = ReactorImportHook()
        with pytest.raises(
            ImportError, match=r"Import of twisted\.internet\.reactor is forbidden"
        ):
            hook.find_spec("twisted.internet.reactor", None)
        assert hook.find_spec("twisted.internet.defer", None) is None

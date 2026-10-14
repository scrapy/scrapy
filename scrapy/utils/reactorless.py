from __future__ import annotations

import contextlib
import sys
from importlib.abc import MetaPathFinder
from typing import TYPE_CHECKING

from scrapy.utils.asyncio import _has_running_loop
from scrapy.utils.reactor import is_reactor_installed

if TYPE_CHECKING:
    from collections.abc import Sequence
    from importlib.machinery import ModuleSpec
    from types import ModuleType


def is_reactorless() -> bool:
    """Check if we are running in the reactorless mode, i.e. with
    :setting:`TWISTED_REACTOR_ENABLED` set to ``False``.

    As this checks the runtime state and not the setting itself, it can be
    wrong when executed very early, before the reactor and/or the asyncio event
    loop are initialized.

    .. note:: As this function uses :func:`asyncio.get_running_loop()`, it will
        only detect the event loop if called in the same thread and from the
        code that runs inside that loop (this shouldn't be a problem when
        calling it from code such as spiders and Scrapy components, if Scrapy
        is run using one of the supported ways).

    .. versionadded:: 2.15.0
    """
    if is_reactor_installed():
        return False
    if _has_running_loop():
        return True
    raise RuntimeError(
        "is_reactorless() called without an installed reactor or running asyncio loop."
    )


class ReactorImportHook(MetaPathFinder):
    """Hook that prevents importing :mod:`twisted.internet.reactor`."""

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        if fullname == "twisted.internet.reactor":
            raise ImportError(
                f"Import of {fullname} is forbidden when running without a Twisted reactor,"
                f" as importing it installs the reactor, which can lead to unexpected behavior."
            )
        return None


def install_reactor_import_hook() -> ReactorImportHook:
    """Prevent importing :mod:`twisted.internet.reactor`.

    The hook is returned and can later be uninstalled with
    :func:`uninstall_reactor_import_hook()`.
    """

    hook = ReactorImportHook()
    sys.meta_path.insert(0, hook)
    return hook


def uninstall_reactor_import_hook(hook: ReactorImportHook) -> None:
    """Uninstall the hook installed with :func:`install_reactor_import_hook()`."""
    with contextlib.suppress(ValueError):
        sys.meta_path.remove(hook)

from __future__ import annotations

import sys
from importlib.abc import MetaPathFinder
from typing import TYPE_CHECKING

from scrapy.utils.asyncio import is_asyncio_available
from scrapy.utils.reactor import is_reactor_installed

if TYPE_CHECKING:
    from collections.abc import Sequence
    from importlib.machinery import ModuleSpec
    from types import ModuleType


def is_reactorless() -> bool:
    """Check if we are running in the reactorless mode, i.e. with
    :setting:`TWISTED_ENABLED` set to ``False``.

    As this checks the runtime state and not the setting itself, it can be
    wrong when executed very early, before the reactor and/or the asyncio event
    loop are initialized.

    .. note:: As this function uses
        :func:`scrapy.utils.asyncio.is_asyncio_available()`, it has the same
        limitations for detecting a running asyncio event loop as that one.

    .. versionadded:: VERSION
    """
    return is_asyncio_available() and not is_reactor_installed()


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


def install_reactor_import_hook() -> None:
    """Prevent importing :mod:`twisted.internet.reactor`."""

    sys.meta_path.insert(0, ReactorImportHook())

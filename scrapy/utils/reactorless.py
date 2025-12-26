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
    return is_asyncio_available() and not is_reactor_installed()


class ReactorImportHook(MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        if fullname == "twisted.internet.reactor":
            raise ImportError(
                f"Import of {fullname} is forbidden in the reactorless mode, to avoid silent problems."
            )
        return None


def install_reactor_import_hook() -> None:
    sys.meta_path.insert(0, ReactorImportHook())

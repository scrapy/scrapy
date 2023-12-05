import importlib
import sys
from contextlib import contextmanager
from types import ModuleType
from typing import Iterator

from pathlib import Path


@contextmanager
def import_cleanup() -> Iterator[None]:
    """
    Clean up the results of importing modules, including the modification
    of :attr:`sys.path` necessary to do so.
    """
    modules = set(sys.modules)
    path = sys.path.copy()
    yield
    for added_module in set(sys.modules) - modules:
        sys.modules.pop(added_module)
    sys.path[:] = path
    importlib.invalidate_caches()


INIT_FILE = '__init__.py'


def import_path(path: Path) -> ModuleType:
    container = path
    while True:
        container = container.parent
        if not (container / INIT_FILE).exists():
            break
    relative = path.relative_to(container)
    if relative.name == INIT_FILE:
        parts = tuple(relative.parts)[:-1]
    else:
        parts = tuple(relative.parts)[:-1]+(relative.stem,)
    module = '.'.join(parts)
    try:
        return importlib.import_module(module)
    except ImportError as e:
        raise ImportError(
            f'{module!r} not importable from {path} as:\n{type(e).__name__}: {e}'
        ) from None

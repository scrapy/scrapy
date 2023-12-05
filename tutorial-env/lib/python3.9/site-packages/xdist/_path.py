import os
from itertools import chain
from pathlib import Path
from typing import Callable, Iterator


def visit_path(
    path: Path, *, filter: Callable[[Path], bool], recurse: Callable[[Path], bool]
) -> Iterator[Path]:
    """
    Implements the interface of ``py.path.local.visit()`` for Path objects,
    to simplify porting the code over from ``py.path.local``.
    """
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [x for x in dirnames if recurse(Path(dirpath, x))]
        for name in chain(dirnames, filenames):
            p = Path(dirpath, name)
            if filter(p):
                yield p

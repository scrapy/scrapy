"""Helper methods related to the CPU."""
from __future__ import annotations

import multiprocessing


def auto_detect_cpus() -> int:
    try:
        n: int | None = multiprocessing.cpu_count()
    except NotImplementedError:
        n = None
    return n if n else 1


__all__ = ("auto_detect_cpus",)

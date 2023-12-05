# -*- test-case-name: twisted.logger.test.test_util -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Logging utilities.
"""

from typing import List

from ._interfaces import LogTrace
from ._logger import Logger


def formatTrace(trace: LogTrace) -> str:
    """
    Format a trace (that is, the contents of the C{log_trace} key of a log
    event) as a visual indication of the message's propagation through various
    observers.

    @param trace: the contents of the C{log_trace} key from an event.

    @return: A multi-line string with indentation and arrows indicating the
        flow of the message through various observers.
    """

    def formatWithName(obj: object) -> str:
        if hasattr(obj, "name"):
            return f"{obj} ({obj.name})"  # type: ignore[attr-defined]
        else:
            return f"{obj}"

    result = []
    lineage: List[Logger] = []

    for parent, child in trace:
        if not lineage or lineage[-1] is not parent:
            if parent in lineage:
                while lineage[-1] is not parent:
                    lineage.pop()

            else:
                if not lineage:
                    result.append(f"{formatWithName(parent)}\n")

                lineage.append(parent)

        result.append("  " * len(lineage))
        result.append(f"-> {formatWithName(child)}\n")

    return "".join(result)

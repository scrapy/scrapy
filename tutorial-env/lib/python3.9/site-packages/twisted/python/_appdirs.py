# -*- test-case-name: twisted.python.test.test_appdirs -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Application data directory support.
"""

import inspect
from typing import cast

import appdirs  # type: ignore[import]

from twisted.python.compat import currentframe


def getDataDirectory(moduleName: str = "") -> str:
    """
    Get a data directory for the caller function, or C{moduleName} if given.

    @param moduleName: The module name if you don't wish to have the caller's
        module.

    @returns: A directory for putting data in.
    """
    if not moduleName:
        caller = currentframe(1)
        module = inspect.getmodule(caller)
        assert module is not None
        moduleName = module.__name__

    return cast(str, appdirs.user_data_dir(moduleName))

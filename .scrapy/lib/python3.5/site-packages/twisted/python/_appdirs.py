# -*- test-case-name: twisted.python.test.test_appdirs -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Application data directory support.
"""

from __future__ import division, absolute_import

import appdirs
import inspect

from twisted.python.compat import currentframe


def getDataDirectory(moduleName=None):
    """
    Get a data directory for the caller function, or C{moduleName} if given.

    @param moduleName: The module name if you don't wish to have the caller's
        module.
    @type moduleName: L{str}

    @returns: A directory for putting data in.
    @rtype: L{str}
    """
    if not moduleName:
        caller = currentframe(1)
        moduleName = inspect.getmodule(caller).__name__

    return appdirs.user_data_dir(moduleName)

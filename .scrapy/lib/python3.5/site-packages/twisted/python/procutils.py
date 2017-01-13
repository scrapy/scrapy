# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Utilities for dealing with processes.
"""

from __future__ import division, absolute_import

import os


def which(name, flags=os.X_OK):
    """
    Search PATH for executable files with the given name.

    On newer versions of MS-Windows, the PATHEXT environment variable will be
    set to the list of file extensions for files considered executable. This
    will normally include things like ".EXE". This function will also find files
    with the given name ending with any of these extensions.

    On MS-Windows the only flag that has any meaning is os.F_OK. Any other
    flags will be ignored.

    @type name: C{str}
    @param name: The name for which to search.

    @type flags: C{int}
    @param flags: Arguments to L{os.access}.

    @rtype: C{list}
    @param: A list of the full paths to files found, in the order in which they
    were found.
    """
    result = []
    exts = list(filter(None, os.environ.get('PATHEXT', '').split(os.pathsep)))
    path = os.environ.get('PATH', None)

    if path is None:
        return []

    for p in os.environ.get('PATH', '').split(os.pathsep):
        p = os.path.join(p, name)
        if os.access(p, flags):
            result.append(p)
        for e in exts:
            pext = p + e
            if os.access(pext, flags):
                result.append(pext)

    return result

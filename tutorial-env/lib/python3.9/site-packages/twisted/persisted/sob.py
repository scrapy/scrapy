# -*- test-case-name: twisted.test.test_sob -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

#
"""
Save and load Small OBjects to and from files, using various formats.

Maintainer: Moshe Zadka
"""


import os
import pickle
import sys

from zope.interface import Interface, implementer

from twisted.persisted import styles
from twisted.python import log, runtime


class IPersistable(Interface):

    """An object which can be saved in several formats to a file"""

    def setStyle(style):
        """Set desired format.

        @type style: string (one of 'pickle' or 'source')
        """

    def save(tag=None, filename=None, passphrase=None):
        """Save object to file.

        @type tag: string
        @type filename: string
        @type passphrase: string
        """


@implementer(IPersistable)
class Persistent:

    style = "pickle"

    def __init__(self, original, name):
        self.original = original
        self.name = name

    def setStyle(self, style):
        """Set desired format.

        @type style: string (one of 'pickle' or 'source')
        """
        self.style = style

    def _getFilename(self, filename, ext, tag):
        if filename:
            finalname = filename
            filename = finalname + "-2"
        elif tag:
            filename = f"{self.name}-{tag}-2.{ext}"
            finalname = f"{self.name}-{tag}.{ext}"
        else:
            filename = f"{self.name}-2.{ext}"
            finalname = f"{self.name}.{ext}"
        return finalname, filename

    def _saveTemp(self, filename, dumpFunc):
        with open(filename, "wb") as f:
            dumpFunc(self.original, f)

    def _getStyle(self):
        if self.style == "source":
            from twisted.persisted.aot import jellyToSource as dumpFunc

            ext = "tas"
        else:

            def dumpFunc(obj, file=None):
                pickle.dump(obj, file, 2)

            ext = "tap"
        return ext, dumpFunc

    def save(self, tag=None, filename=None, passphrase=None):
        """Save object to file.

        @type tag: string
        @type filename: string
        @type passphrase: string
        """
        ext, dumpFunc = self._getStyle()
        if passphrase is not None:
            raise TypeError("passphrase must be None")
        finalname, filename = self._getFilename(filename, ext, tag)
        log.msg("Saving " + self.name + " application to " + finalname + "...")
        self._saveTemp(filename, dumpFunc)
        if runtime.platformType == "win32" and os.path.isfile(finalname):
            os.remove(finalname)
        os.rename(filename, finalname)
        log.msg("Saved.")


# "Persistant" has been present since 1.0.7, so retain it for compatibility
Persistant = Persistent


class _EverythingEphemeral(styles.Ephemeral):

    initRun = 0

    def __init__(self, mainMod):
        """
        @param mainMod: The '__main__' module that this class will proxy.
        """
        self.mainMod = mainMod

    def __getattr__(self, key):
        try:
            return getattr(self.mainMod, key)
        except AttributeError:
            if self.initRun:
                raise
            else:
                log.msg("Warning!  Loading from __main__: %s" % key)
                return styles.Ephemeral()


def load(filename, style):
    """Load an object from a file.

    Deserialize an object from a file. The file can be encrypted.

    @param filename: string
    @param style: string (one of 'pickle' or 'source')
    """
    mode = "r"
    if style == "source":
        from twisted.persisted.aot import unjellyFromSource as _load
    else:
        _load, mode = pickle.load, "rb"

    fp = open(filename, mode)
    ee = _EverythingEphemeral(sys.modules["__main__"])
    sys.modules["__main__"] = ee
    ee.initRun = 1
    with fp:
        try:
            value = _load(fp)
        finally:
            # restore __main__ if an exception is raised.
            sys.modules["__main__"] = ee.mainMod

    styles.doUpgrade()
    ee.initRun = 0
    persistable = IPersistable(value, None)
    if persistable is not None:
        persistable.setStyle(style)
    return value


def loadValueFromFile(filename, variable):
    """Load the value of a variable in a Python file.

    Run the contents of the file in a namespace and return the result of the
    variable named C{variable}.

    @param filename: string
    @param variable: string
    """
    with open(filename) as fileObj:
        data = fileObj.read()
    d = {"__file__": filename}
    codeObj = compile(data, filename, "exec")
    eval(codeObj, d, d)
    value = d[variable]
    return value


def guessType(filename):
    ext = os.path.splitext(filename)[1]
    return {
        ".tac": "python",
        ".etac": "python",
        ".py": "python",
        ".tap": "pickle",
        ".etap": "pickle",
        ".tas": "source",
        ".etas": "source",
    }[ext]


__all__ = [
    "loadValueFromFile",
    "load",
    "Persistent",
    "Persistant",
    "IPersistable",
    "guessType",
]

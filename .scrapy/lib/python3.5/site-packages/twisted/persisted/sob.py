# -*- test-case-name: twisted.test.test_sob -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

#
"""
Save and load Small OBjects to and from files, using various formats.

Maintainer: Moshe Zadka
"""

from __future__ import division, absolute_import

import os
import sys
import warnings

try:
    import cPickle as pickle
except ImportError:
    import pickle
from io import BytesIO
from hashlib import md5
from twisted.python import log, runtime
from twisted.persisted import styles
from zope.interface import implementer, Interface

# Note:
# These encrypt/decrypt functions only work for data formats
# which are immune to having spaces tucked at the end.
# All data formats which persist saves hold that condition.
def _encrypt(passphrase, data):
    from Crypto.Cipher import AES as cipher

    warnings.warn(
        'Saving encrypted persisted data is deprecated since Twisted 15.5.0',
        DeprecationWarning, stacklevel=2)

    leftover = len(data) % cipher.block_size
    if leftover:
        data += b' ' * (cipher.block_size - leftover)
    return cipher.new(md5(passphrase).digest()[:16]).encrypt(data)



def _decrypt(passphrase, data):
    from Crypto.Cipher import AES

    warnings.warn(
        'Loading encrypted persisted data is deprecated since Twisted 15.5.0',
        DeprecationWarning, stacklevel=2)

    return AES.new(md5(passphrase).digest()[:16]).decrypt(data)



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
            filename = "%s-%s-2.%s" % (self.name, tag, ext)
            finalname = "%s-%s.%s" % (self.name, tag, ext)
        else:
            filename = "%s-2.%s" % (self.name, ext)
            finalname = "%s.%s" % (self.name, ext)
        return finalname, filename

    def _saveTemp(self, filename, passphrase, dumpFunc):
        with open(filename, 'wb') as f:
            if passphrase is None:
                dumpFunc(self.original, f)
            else:
                s = BytesIO()
                dumpFunc(self.original, s)
                f.write(_encrypt(passphrase, s.getvalue()))

    def _getStyle(self):
        if self.style == "source":
            from twisted.persisted.aot import jellyToSource as dumpFunc
            ext = "tas"
        else:
            def dumpFunc(obj, file):
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
        if passphrase:
            ext = 'e' + ext
        finalname, filename = self._getFilename(filename, ext, tag)
        log.msg("Saving "+self.name+" application to "+finalname+"...")
        self._saveTemp(filename, passphrase, dumpFunc)
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


def load(filename, style, passphrase=None):
    """Load an object from a file.

    Deserialize an object from a file. The file can be encrypted.

    @param filename: string
    @param style: string (one of 'pickle' or 'source')
    @param passphrase: string
    """
    mode = 'r'
    if style=='source':
        from twisted.persisted.aot import unjellyFromSource as _load
    else:
        _load, mode = pickle.load, 'rb'
    if passphrase:
        with open(filename, 'rb') as loadedFile:
            fp = BytesIO(_decrypt(passphrase, loadedFile.read()))
    else:
        fp = open(filename, mode)
    ee = _EverythingEphemeral(sys.modules['__main__'])
    sys.modules['__main__'] = ee
    ee.initRun = 1
    with fp:
        try:
            value = _load(fp)
        finally:
            # restore __main__ if an exception is raised.
            sys.modules['__main__'] = ee.mainMod

    styles.doUpgrade()
    ee.initRun = 0
    persistable = IPersistable(value, None)
    if persistable is not None:
        persistable.setStyle(style)
    return value


def loadValueFromFile(filename, variable, passphrase=None):
    """Load the value of a variable in a Python file.

    Run the contents of the file, after decrypting if C{passphrase} is
    given, in a namespace and return the result of the variable
    named C{variable}.

    @param filename: string
    @param variable: string
    @param passphrase: string
    """
    if passphrase:
        mode = 'rb'
    else:
        mode = 'r'
    with open(filename, mode) as fileObj:
        data = fileObj.read()
    d = {'__file__': filename}
    if passphrase:
        data = _decrypt(passphrase, data)
    codeObj = compile(data, filename, "exec")
    eval(codeObj, d, d)
    value = d[variable]
    return value

def guessType(filename):
    ext = os.path.splitext(filename)[1]
    return {
        '.tac':  'python',
        '.etac':  'python',
        '.py':  'python',
        '.tap': 'pickle',
        '.etap': 'pickle',
        '.tas': 'source',
        '.etas': 'source',
    }[ext]

__all__ = ['loadValueFromFile', 'load', 'Persistent', 'Persistant',
           'IPersistable', 'guessType']

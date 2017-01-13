# -*- test-case-name: twisted.test.test_strcred -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Cred plugin for a file of the format 'username:password'.
"""

from __future__ import absolute_import, division

import sys

from zope.interface import implementer

from twisted import plugin
from twisted.cred.checkers import FilePasswordDB
from twisted.cred.strcred import ICheckerFactory
from twisted.cred.credentials import IUsernamePassword, IUsernameHashedPassword



fileCheckerFactoryHelp = """
This checker expects to receive the location of a file that
conforms to the FilePasswordDB format. Each line in the file
should be of the format 'username:password', in plain text.
"""

invalidFileWarning = 'Warning: not a valid file'


@implementer(ICheckerFactory, plugin.IPlugin)
class FileCheckerFactory(object):
    """
    A factory for instances of L{FilePasswordDB}.
    """
    authType = 'file'
    authHelp = fileCheckerFactoryHelp
    argStringFormat = 'Location of a FilePasswordDB-formatted file.'
    # Explicitly defined here because FilePasswordDB doesn't do it for us
    credentialInterfaces = (IUsernamePassword, IUsernameHashedPassword)

    errorOutput = sys.stderr

    def generateChecker(self, argstring):
        """
        This checker factory expects to get the location of a file.
        The file should conform to the format required by
        L{FilePasswordDB} (using defaults for all
        initialization parameters).
        """
        from twisted.python.filepath import FilePath
        if not argstring.strip():
            raise ValueError('%r requires a filename' % self.authType)
        elif not FilePath(argstring).isfile():
            self.errorOutput.write('%s: %s\n' % (invalidFileWarning, argstring))
        return FilePasswordDB(argstring)



theFileCheckerFactory = FileCheckerFactory()

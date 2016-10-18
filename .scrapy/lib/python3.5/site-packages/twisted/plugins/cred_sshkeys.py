# -*- test-case-name: twisted.test.test_strcred -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Cred plugin for ssh key login.
"""

from __future__ import absolute_import, division

from zope.interface import implementer

from twisted import plugin
from twisted.cred.strcred import ICheckerFactory


sshKeyCheckerFactoryHelp = """
This allows SSH public key authentication, based on public keys listed in
authorized_keys and authorized_keys2 files in user .ssh/ directories.
"""


try:
    from twisted.conch.checkers import (
        SSHPublicKeyChecker, UNIXAuthorizedKeysFiles)

    @implementer(ICheckerFactory, plugin.IPlugin)
    class SSHKeyCheckerFactory(object):
        """
        Generates checkers that will authenticate a SSH public key
        """
        authType = 'sshkey'
        authHelp = sshKeyCheckerFactoryHelp
        argStringFormat = 'No argstring required.'
        credentialInterfaces = SSHPublicKeyChecker.credentialInterfaces


        def generateChecker(self, argstring=''):
            """
            This checker factory ignores the argument string. Everything
            needed to authenticate users is pulled out of the public keys
            listed in user .ssh/ directories.
            """
            return SSHPublicKeyChecker(UNIXAuthorizedKeysFiles())



    theSSHKeyCheckerFactory = SSHKeyCheckerFactory()

except ImportError:
    # if checkers can't be imported, then there should be no SSH cred plugin
    pass

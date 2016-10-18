# -*- test-case-name: twisted.test.test_strcred -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Cred plugin for anonymous logins.
"""

from __future__ import absolute_import, division

from zope.interface import implementer

from twisted import plugin
from twisted.cred.checkers import AllowAnonymousAccess
from twisted.cred.strcred import ICheckerFactory
from twisted.cred.credentials import IAnonymous


anonymousCheckerFactoryHelp = """
This allows anonymous authentication for servers that support it.
"""


@implementer(ICheckerFactory, plugin.IPlugin)
class AnonymousCheckerFactory(object):
    """
    Generates checkers that will authenticate an anonymous request.
    """
    authType = 'anonymous'
    authHelp = anonymousCheckerFactoryHelp
    argStringFormat = 'No argstring required.'
    credentialInterfaces = (IAnonymous,)


    def generateChecker(self, argstring=''):
        return AllowAnonymousAccess()



theAnonymousCheckerFactory = AnonymousCheckerFactory()

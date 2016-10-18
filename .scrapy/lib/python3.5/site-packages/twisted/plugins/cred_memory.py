# -*- test-case-name: twisted.test.test_strcred -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Cred plugin for an in-memory user database.
"""

from __future__ import absolute_import, division

from zope.interface import implementer

from twisted import plugin
from twisted.cred.strcred import ICheckerFactory
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from twisted.cred.credentials import IUsernamePassword, IUsernameHashedPassword



inMemoryCheckerFactoryHelp = """
A checker that uses an in-memory user database.

This is only of use in one-off test programs or examples which
don't want to focus too much on how credentials are verified. You
really don't want to use this for anything else. It is a toy.
"""



@implementer(ICheckerFactory, plugin.IPlugin)
class InMemoryCheckerFactory(object):
    """
    A factory for in-memory credentials checkers.

    This is only of use in one-off test programs or examples which don't
    want to focus too much on how credentials are verified.

    You really don't want to use this for anything else.  It is, at best, a
    toy.  If you need a simple credentials checker for a real application,
    see L{cred_file.FileCheckerFactory}.
    """
    authType = 'memory'
    authHelp = inMemoryCheckerFactoryHelp
    argStringFormat = 'A colon-separated list (name:password:...)'
    credentialInterfaces = (IUsernamePassword,
                            IUsernameHashedPassword)

    def generateChecker(self, argstring):
        """
        This checker factory expects to get a list of
        username:password pairs, with each pair also separated by a
        colon. For example, the string 'alice:f:bob:g' would generate
        two users, one named 'alice' and one named 'bob'.
        """
        checker = InMemoryUsernamePasswordDatabaseDontUse()
        if argstring:
            pieces = argstring.split(':')
            if len(pieces) % 2:
                from twisted.cred.strcred import InvalidAuthArgumentString
                raise InvalidAuthArgumentString(
                    "argstring must be in format U:P:...")
            for i in range(0, len(pieces), 2):
                username, password = pieces[i], pieces[i+1]
                checker.addUser(username, password)
        return checker



theInMemoryCheckerFactory = InMemoryCheckerFactory()

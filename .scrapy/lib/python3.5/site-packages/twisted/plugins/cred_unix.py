# -*- test-case-name: twisted.test.test_strcred -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Cred plugin for UNIX user accounts.
"""

from __future__ import absolute_import, division

from zope.interface import implementer

from twisted import plugin
from twisted.cred.strcred import ICheckerFactory
from twisted.cred.checkers import ICredentialsChecker
from twisted.cred.credentials import IUsernamePassword
from twisted.cred.error import UnauthorizedLogin
from twisted.internet import defer



def verifyCryptedPassword(crypted, pw):
    if crypted[0] == '$': # md5_crypt encrypted
        salt = '$1$' + crypted.split('$')[2]
    else:
        salt = crypted[:2]
    try:
        import crypt
    except ImportError:
        crypt = None

    if crypt is None:
        raise NotImplementedError("cred_unix not supported on this platform")
    return crypt.crypt(pw, salt) == crypted



@implementer(ICredentialsChecker)
class UNIXChecker(object):
    """
    A credentials checker for a UNIX server. This will check that
    an authenticating username/password is a valid user on the system.

    Does not work on Windows.

    Right now this supports Python's pwd and spwd modules, if they are
    installed. It does not support PAM.
    """
    credentialInterfaces = (IUsernamePassword,)


    def checkPwd(self, pwd, username, password):
        try:
            cryptedPass = pwd.getpwnam(username)[1]
        except KeyError:
            return defer.fail(UnauthorizedLogin())
        else:
            if cryptedPass in ('*', 'x'):
                # Allow checkSpwd to take over
                return None
            elif verifyCryptedPassword(cryptedPass, password):
                return defer.succeed(username)


    def checkSpwd(self, spwd, username, password):
        try:
            cryptedPass = spwd.getspnam(username)[1]
        except KeyError:
            return defer.fail(UnauthorizedLogin())
        else:
            if verifyCryptedPassword(cryptedPass, password):
                return defer.succeed(username)


    def requestAvatarId(self, credentials):
        username, password = credentials.username, credentials.password

        try:
            import pwd
        except ImportError:
            pwd = None

        if pwd is not None:
            checked = self.checkPwd(pwd, username, password)
            if checked is not None:
                return checked

        try:
            import spwd
        except ImportError:
            spwd = None

        if spwd is not None:
            checked = self.checkSpwd(spwd, username, password)
            if checked is not None:
                return checked
        # TODO: check_pam?
        # TODO: check_shadow?
        return defer.fail(UnauthorizedLogin())



unixCheckerFactoryHelp = """
This checker will attempt to use every resource available to
authenticate against the list of users on the local UNIX system.
(This does not support Windows servers for very obvious reasons.)

Right now, this includes support for:

  * Python's pwd module (which checks /etc/passwd)
  * Python's spwd module (which checks /etc/shadow)

Future versions may include support for PAM authentication.
"""


@implementer(ICheckerFactory, plugin.IPlugin)
class UNIXCheckerFactory(object):
    """
    A factory for L{UNIXChecker}.
    """
    authType = 'unix'
    authHelp = unixCheckerFactoryHelp
    argStringFormat = 'No argstring required.'
    credentialInterfaces = UNIXChecker.credentialInterfaces

    def generateChecker(self, argstring):
        """
        This checker factory ignores the argument string. Everything
        needed to generate a user database is pulled out of the local
        UNIX environment.
        """
        return UNIXChecker()



theUnixCheckerFactory = UNIXCheckerFactory()

# -*- test-case-name: twisted.test.test_strcred -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Cred plugin for UNIX user accounts.
"""


from zope.interface import implementer

from twisted import plugin
from twisted.cred.checkers import ICredentialsChecker
from twisted.cred.credentials import IUsernamePassword
from twisted.cred.error import UnauthorizedLogin
from twisted.cred.strcred import ICheckerFactory
from twisted.internet import defer


def verifyCryptedPassword(crypted, pw):
    """
    Use L{crypt.crypt} to Verify that an unencrypted
    password matches the encrypted password.

    @param crypted: The encrypted password, obtained from
                    the Unix password database or Unix shadow
                    password database.
    @param pw: The unencrypted password.
    @return: L{True} if there is successful match, else L{False}.
    @rtype: L{bool}
    """
    try:
        import crypt
    except ImportError:
        crypt = None

    if crypt is None:
        raise NotImplementedError("cred_unix not supported on this platform")
    if isinstance(pw, bytes):
        pw = pw.decode("utf-8")
    if isinstance(crypted, bytes):
        crypted = crypted.decode("utf-8")
    try:
        crypted_check = crypt.crypt(pw, crypted)
        if isinstance(crypted_check, bytes):
            crypted_check = crypted_check.decode("utf-8")
        return crypted_check == crypted
    except OSError:
        return False


@implementer(ICredentialsChecker)
class UNIXChecker:
    """
    A credentials checker for a UNIX server. This will check that
    an authenticating username/password is a valid user on the system.

    Does not work on Windows.

    Right now this supports Python's pwd and spwd modules, if they are
    installed. It does not support PAM.
    """

    credentialInterfaces = (IUsernamePassword,)

    def checkPwd(self, pwd, username, password):
        """
        Obtain the encrypted password for C{username} from the Unix password
        database using L{pwd.getpwnam}, and see if it it matches it matches
        C{password}.

        @param pwd: Module which provides functions which
                    access to the Unix password database.
        @type pwd: C{module}
        @param username: The user to look up in the Unix password database.
        @type username: L{unicode}/L{str} or L{bytes}
        @param password: The password to compare.
        @type username: L{unicode}/L{str} or L{bytes}
        """
        try:
            if isinstance(username, bytes):
                username = username.decode("utf-8")
            cryptedPass = pwd.getpwnam(username).pw_passwd
        except KeyError:
            return defer.fail(UnauthorizedLogin())
        else:
            if cryptedPass in ("*", "x"):
                # Allow checkSpwd to take over
                return None
            elif verifyCryptedPassword(cryptedPass, password):
                return defer.succeed(username)

    def checkSpwd(self, spwd, username, password):
        """
        Obtain the encrypted password for C{username} from the
        Unix shadow password database using L{spwd.getspnam},
        and see if it it matches it matches C{password}.

        @param spwd: Module which provides functions which
                     access to the Unix shadow password database.
        @type spwd: C{module}
        @param username: The user to look up in the Unix password database.
        @type username: L{unicode}/L{str} or L{bytes}
        @param password: The password to compare.
        @type username: L{unicode}/L{str} or L{bytes}
        """
        try:
            if isinstance(username, bytes):
                username = username.decode("utf-8")
            if getattr(spwd.struct_spwd, "sp_pwdp", None):
                # Python 3
                cryptedPass = spwd.getspnam(username).sp_pwdp
            else:
                # Python 2
                cryptedPass = spwd.getspnam(username).sp_pwd
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
class UNIXCheckerFactory:
    """
    A factory for L{UNIXChecker}.
    """

    authType = "unix"
    authHelp = unixCheckerFactoryHelp
    argStringFormat = "No argstring required."
    credentialInterfaces = UNIXChecker.credentialInterfaces

    def generateChecker(self, argstring):
        """
        This checker factory ignores the argument string. Everything
        needed to generate a user database is pulled out of the local
        UNIX environment.
        """
        return UNIXChecker()


theUnixCheckerFactory = UNIXCheckerFactory()

# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.conch.checkers}.
"""


import os
from base64 import encodebytes
from collections import namedtuple
from io import BytesIO
from typing import Optional

cryptSkip: Optional[str]
try:
    import crypt
except ImportError:
    cryptSkip = "cannot run without crypt module"
else:
    cryptSkip = None

from zope.interface.verify import verifyObject

from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from twisted.cred.credentials import (
    ISSHPrivateKey,
    IUsernamePassword,
    SSHPrivateKey,
    UsernamePassword,
)
from twisted.cred.error import UnauthorizedLogin, UnhandledCredentials
from twisted.internet.defer import Deferred
from twisted.python import util
from twisted.python.fakepwd import ShadowDatabase, UserDatabase
from twisted.python.filepath import FilePath
from twisted.python.reflect import requireModule
from twisted.test.test_process import MockOS
from twisted.trial.unittest import TestCase

if requireModule("cryptography") and requireModule("pyasn1"):
    dependencySkip = None
    from twisted.conch import checkers
    from twisted.conch.error import NotEnoughAuthentication, ValidPublicKey
    from twisted.conch.ssh import keys
    from twisted.conch.test import keydata
else:
    dependencySkip = "can't run without cryptography and PyASN1"

if getattr(os, "geteuid", None) is not None:
    euidSkip = None
else:
    euidSkip = "Cannot run without effective UIDs (questionable)"


class HelperTests(TestCase):
    """
    Tests for helper functions L{verifyCryptedPassword}, L{_pwdGetByName} and
    L{_shadowGetByName}.
    """

    skip = cryptSkip or dependencySkip

    def setUp(self):
        self.mockos = MockOS()

    def test_verifyCryptedPassword(self):
        """
        L{verifyCryptedPassword} returns C{True} if the plaintext password
        passed to it matches the encrypted password passed to it.
        """
        password = "secret string"
        salt = "salty"
        crypted = crypt.crypt(password, salt)
        self.assertTrue(
            checkers.verifyCryptedPassword(crypted, password),
            "{!r} supposed to be valid encrypted password for {!r}".format(
                crypted, password
            ),
        )

    def test_verifyCryptedPasswordMD5(self):
        """
        L{verifyCryptedPassword} returns True if the provided cleartext password
        matches the provided MD5 password hash.
        """
        password = "password"
        salt = "$1$salt"
        crypted = crypt.crypt(password, salt)
        self.assertTrue(
            checkers.verifyCryptedPassword(crypted, password),
            "{!r} supposed to be valid encrypted password for {}".format(
                crypted, password
            ),
        )

    def test_refuteCryptedPassword(self):
        """
        L{verifyCryptedPassword} returns C{False} if the plaintext password
        passed to it does not match the encrypted password passed to it.
        """
        password = "string secret"
        wrong = "secret string"
        crypted = crypt.crypt(password, password)
        self.assertFalse(
            checkers.verifyCryptedPassword(crypted, wrong),
            "{!r} not supposed to be valid encrypted password for {}".format(
                crypted, wrong
            ),
        )

    def test_pwdGetByName(self):
        """
        L{_pwdGetByName} returns a tuple of items from the UNIX /etc/passwd
        database if the L{pwd} module is present.
        """
        userdb = UserDatabase()
        userdb.addUser("alice", "secrit", 1, 2, "first last", "/foo", "/bin/sh")
        self.patch(checkers, "pwd", userdb)
        self.assertEqual(checkers._pwdGetByName("alice"), userdb.getpwnam("alice"))

    def test_pwdGetByNameWithoutPwd(self):
        """
        If the C{pwd} module isn't present, L{_pwdGetByName} returns L{None}.
        """
        self.patch(checkers, "pwd", None)
        self.assertIsNone(checkers._pwdGetByName("alice"))

    def test_shadowGetByName(self):
        """
        L{_shadowGetByName} returns a tuple of items from the UNIX /etc/shadow
        database if the L{spwd} is present.
        """
        userdb = ShadowDatabase()
        userdb.addUser("bob", "passphrase", 1, 2, 3, 4, 5, 6, 7)
        self.patch(checkers, "spwd", userdb)

        self.mockos.euid = 2345
        self.mockos.egid = 1234
        self.patch(util, "os", self.mockos)

        self.assertEqual(checkers._shadowGetByName("bob"), userdb.getspnam("bob"))
        self.assertEqual(self.mockos.seteuidCalls, [0, 2345])
        self.assertEqual(self.mockos.setegidCalls, [0, 1234])

    def test_shadowGetByNameWithoutSpwd(self):
        """
        L{_shadowGetByName} returns L{None} if C{spwd} is not present.
        """
        self.patch(checkers, "spwd", None)

        self.assertIsNone(checkers._shadowGetByName("bob"))
        self.assertEqual(self.mockos.seteuidCalls, [])
        self.assertEqual(self.mockos.setegidCalls, [])


class SSHPublicKeyDatabaseTests(TestCase):
    """
    Tests for L{SSHPublicKeyDatabase}.
    """

    skip = euidSkip or dependencySkip

    def setUp(self) -> None:
        self.checker = checkers.SSHPublicKeyDatabase()
        self.key1 = encodebytes(b"foobar")
        self.key2 = encodebytes(b"eggspam")
        self.content = b"t1 " + self.key1 + b" foo\nt2 " + self.key2 + b" egg\n"

        self.mockos = MockOS()
        self.patch(util, "os", self.mockos)

        self.path = FilePath(self.mktemp())
        assert isinstance(self.path.path, str)  # text mode
        self.sshDir = self.path.child(".ssh")
        self.sshDir.makedirs()

        userdb = UserDatabase()
        userdb.addUser(
            "user",
            "password",
            1,
            2,
            "first last",
            self.path.path,
            "/bin/shell",
        )
        self.checker._userdb = userdb  # type: ignore

    def test_deprecated(self):
        """
        L{SSHPublicKeyDatabase} is deprecated as of version 15.0
        """
        warningsShown = self.flushWarnings(offendingFunctions=[self.setUp])
        self.assertEqual(warningsShown[0]["category"], DeprecationWarning)
        self.assertEqual(
            warningsShown[0]["message"],
            "twisted.conch.checkers.SSHPublicKeyDatabase "
            "was deprecated in Twisted 15.0.0: Please use "
            "twisted.conch.checkers.SSHPublicKeyChecker, "
            "initialized with an instance of "
            "twisted.conch.checkers.UNIXAuthorizedKeysFiles instead.",
        )
        self.assertEqual(len(warningsShown), 1)

    def _testCheckKey(self, filename):
        self.sshDir.child(filename).setContent(self.content)
        user = UsernamePassword(b"user", b"password")
        user.blob = b"foobar"
        self.assertTrue(self.checker.checkKey(user))
        user.blob = b"eggspam"
        self.assertTrue(self.checker.checkKey(user))
        user.blob = b"notallowed"
        self.assertFalse(self.checker.checkKey(user))

    def test_checkKey(self):
        """
        L{SSHPublicKeyDatabase.checkKey} should retrieve the content of the
        authorized_keys file and check the keys against that file.
        """
        self._testCheckKey("authorized_keys")
        self.assertEqual(self.mockos.seteuidCalls, [])
        self.assertEqual(self.mockos.setegidCalls, [])

    def test_checkKey2(self):
        """
        L{SSHPublicKeyDatabase.checkKey} should retrieve the content of the
        authorized_keys2 file and check the keys against that file.
        """
        self._testCheckKey("authorized_keys2")
        self.assertEqual(self.mockos.seteuidCalls, [])
        self.assertEqual(self.mockos.setegidCalls, [])

    def test_checkKeyAsRoot(self):
        """
        If the key file is readable, L{SSHPublicKeyDatabase.checkKey} should
        switch its uid/gid to the ones of the authenticated user.
        """
        keyFile = self.sshDir.child("authorized_keys")
        keyFile.setContent(self.content)
        # Fake permission error by changing the mode
        keyFile.chmod(0o000)
        self.addCleanup(keyFile.chmod, 0o777)
        # And restore the right mode when seteuid is called
        savedSeteuid = self.mockos.seteuid

        def seteuid(euid):
            keyFile.chmod(0o777)
            return savedSeteuid(euid)

        self.mockos.euid = 2345
        self.mockos.egid = 1234
        self.patch(self.mockos, "seteuid", seteuid)
        self.patch(util, "os", self.mockos)
        user = UsernamePassword(b"user", b"password")
        user.blob = b"foobar"
        self.assertTrue(self.checker.checkKey(user))
        self.assertEqual(self.mockos.seteuidCalls, [0, 1, 0, 2345])
        self.assertEqual(self.mockos.setegidCalls, [2, 1234])

    def test_requestAvatarId(self):
        """
        L{SSHPublicKeyDatabase.requestAvatarId} should return the avatar id
        passed in if its C{_checkKey} method returns True.
        """

        def _checkKey(ignored):
            return True

        self.patch(self.checker, "checkKey", _checkKey)
        credentials = SSHPrivateKey(
            b"test",
            b"ssh-rsa",
            keydata.publicRSA_openssh,
            b"foo",
            keys.Key.fromString(keydata.privateRSA_openssh).sign(b"foo"),
        )
        d = self.checker.requestAvatarId(credentials)

        def _verify(avatarId):
            self.assertEqual(avatarId, b"test")

        return d.addCallback(_verify)

    def test_requestAvatarIdWithoutSignature(self):
        """
        L{SSHPublicKeyDatabase.requestAvatarId} should raise L{ValidPublicKey}
        if the credentials represent a valid key without a signature.  This
        tells the user that the key is valid for login, but does not actually
        allow that user to do so without a signature.
        """

        def _checkKey(ignored):
            return True

        self.patch(self.checker, "checkKey", _checkKey)
        credentials = SSHPrivateKey(
            b"test", b"ssh-rsa", keydata.publicRSA_openssh, None, None
        )
        d = self.checker.requestAvatarId(credentials)
        return self.assertFailure(d, ValidPublicKey)

    def test_requestAvatarIdInvalidKey(self):
        """
        If L{SSHPublicKeyDatabase.checkKey} returns False,
        C{_cbRequestAvatarId} should raise L{UnauthorizedLogin}.
        """

        def _checkKey(ignored):
            return False

        self.patch(self.checker, "checkKey", _checkKey)
        d = self.checker.requestAvatarId(None)
        return self.assertFailure(d, UnauthorizedLogin)

    def test_requestAvatarIdInvalidSignature(self):
        """
        Valid keys with invalid signatures should cause
        L{SSHPublicKeyDatabase.requestAvatarId} to return a {UnauthorizedLogin}
        failure
        """

        def _checkKey(ignored):
            return True

        self.patch(self.checker, "checkKey", _checkKey)
        credentials = SSHPrivateKey(
            b"test",
            b"ssh-rsa",
            keydata.publicRSA_openssh,
            b"foo",
            keys.Key.fromString(keydata.privateDSA_openssh).sign(b"foo"),
        )
        d = self.checker.requestAvatarId(credentials)
        return self.assertFailure(d, UnauthorizedLogin)

    def test_requestAvatarIdNormalizeException(self):
        """
        Exceptions raised while verifying the key should be normalized into an
        C{UnauthorizedLogin} failure.
        """

        def _checkKey(ignored):
            return True

        self.patch(self.checker, "checkKey", _checkKey)
        credentials = SSHPrivateKey(b"test", None, b"blob", b"sigData", b"sig")
        d = self.checker.requestAvatarId(credentials)

        def _verifyLoggedException(failure):
            errors = self.flushLoggedErrors(keys.BadKeyError)
            self.assertEqual(len(errors), 1)
            return failure

        d.addErrback(_verifyLoggedException)
        return self.assertFailure(d, UnauthorizedLogin)


class SSHProtocolCheckerTests(TestCase):
    """
    Tests for L{SSHProtocolChecker}.
    """

    skip = dependencySkip

    def test_registerChecker(self):
        """
        L{SSHProcotolChecker.registerChecker} should add the given checker to
        the list of registered checkers.
        """
        checker = checkers.SSHProtocolChecker()
        self.assertEqual(checker.credentialInterfaces, [])
        checker.registerChecker(
            checkers.SSHPublicKeyDatabase(),
        )
        self.assertEqual(checker.credentialInterfaces, [ISSHPrivateKey])
        self.assertIsInstance(
            checker.checkers[ISSHPrivateKey], checkers.SSHPublicKeyDatabase
        )

    def test_registerCheckerWithInterface(self):
        """
        If a specific interface is passed into
        L{SSHProtocolChecker.registerChecker}, that interface should be
        registered instead of what the checker specifies in
        credentialIntefaces.
        """
        checker = checkers.SSHProtocolChecker()
        self.assertEqual(checker.credentialInterfaces, [])
        checker.registerChecker(checkers.SSHPublicKeyDatabase(), IUsernamePassword)
        self.assertEqual(checker.credentialInterfaces, [IUsernamePassword])
        self.assertIsInstance(
            checker.checkers[IUsernamePassword], checkers.SSHPublicKeyDatabase
        )

    def test_requestAvatarId(self):
        """
        L{SSHProtocolChecker.requestAvatarId} should defer to one if its
        registered checkers to authenticate a user.
        """
        checker = checkers.SSHProtocolChecker()
        passwordDatabase = InMemoryUsernamePasswordDatabaseDontUse()
        passwordDatabase.addUser(b"test", b"test")
        checker.registerChecker(passwordDatabase)
        d = checker.requestAvatarId(UsernamePassword(b"test", b"test"))

        def _callback(avatarId):
            self.assertEqual(avatarId, b"test")

        return d.addCallback(_callback)

    def test_requestAvatarIdWithNotEnoughAuthentication(self):
        """
        If the client indicates that it is never satisfied, by always returning
        False from _areDone, then L{SSHProtocolChecker} should raise
        L{NotEnoughAuthentication}.
        """
        checker = checkers.SSHProtocolChecker()

        def _areDone(avatarId):
            return False

        self.patch(checker, "areDone", _areDone)

        passwordDatabase = InMemoryUsernamePasswordDatabaseDontUse()
        passwordDatabase.addUser(b"test", b"test")
        checker.registerChecker(passwordDatabase)
        d = checker.requestAvatarId(UsernamePassword(b"test", b"test"))
        return self.assertFailure(d, NotEnoughAuthentication)

    def test_requestAvatarIdInvalidCredential(self):
        """
        If the passed credentials aren't handled by any registered checker,
        L{SSHProtocolChecker} should raise L{UnhandledCredentials}.
        """
        checker = checkers.SSHProtocolChecker()
        d = checker.requestAvatarId(UsernamePassword(b"test", b"test"))
        return self.assertFailure(d, UnhandledCredentials)

    def test_areDone(self):
        """
        The default L{SSHProcotolChecker.areDone} should simply return True.
        """
        self.assertTrue(checkers.SSHProtocolChecker().areDone(None))


class UNIXPasswordDatabaseTests(TestCase):
    """
    Tests for L{UNIXPasswordDatabase}.
    """

    skip = cryptSkip or dependencySkip

    def assertLoggedIn(self, d: Deferred[bytes], username: bytes) -> None:
        """
        Assert that the L{Deferred} passed in is called back with the value
        'username'.  This represents a valid login for this TestCase.

        @param d: a L{Deferred} from an L{IChecker.requestAvatarId} method.
        """
        self.assertEqual(self.successResultOf(d), username)

    def test_defaultCheckers(self):
        """
        L{UNIXPasswordDatabase} with no arguments has checks the C{pwd} database
        and then the C{spwd} database.
        """
        checker = checkers.UNIXPasswordDatabase()

        def crypted(username, password):
            salt = crypt.crypt(password, username)
            crypted = crypt.crypt(password, "$1$" + salt)
            return crypted

        pwd = UserDatabase()
        pwd.addUser(
            "alice", crypted("alice", "password"), 1, 2, "foo", "/foo", "/bin/sh"
        )
        # x and * are convention for "look elsewhere for the password"
        pwd.addUser("bob", "x", 1, 2, "bar", "/bar", "/bin/sh")
        spwd = ShadowDatabase()
        spwd.addUser("alice", "wrong", 1, 2, 3, 4, 5, 6, 7)
        spwd.addUser("bob", crypted("bob", "password"), 8, 9, 10, 11, 12, 13, 14)

        self.patch(checkers, "pwd", pwd)
        self.patch(checkers, "spwd", spwd)

        mockos = MockOS()
        self.patch(util, "os", mockos)

        mockos.euid = 2345
        mockos.egid = 1234

        cred = UsernamePassword(b"alice", b"password")
        self.assertLoggedIn(checker.requestAvatarId(cred), b"alice")
        self.assertEqual(mockos.seteuidCalls, [])
        self.assertEqual(mockos.setegidCalls, [])
        cred.username = b"bob"
        self.assertLoggedIn(checker.requestAvatarId(cred), b"bob")
        self.assertEqual(mockos.seteuidCalls, [0, 2345])
        self.assertEqual(mockos.setegidCalls, [0, 1234])

    def assertUnauthorizedLogin(self, d):
        """
        Asserts that the L{Deferred} passed in is erred back with an
        L{UnauthorizedLogin} L{Failure}.  This reprsents an invalid login for
        this TestCase.

        NOTE: To work, this method's return value must be returned from the
        test method, or otherwise hooked up to the test machinery.

        @param d: a L{Deferred} from an L{IChecker.requestAvatarId} method.
        @type d: L{Deferred}
        @rtype: L{None}
        """
        self.failureResultOf(d, checkers.UnauthorizedLogin)

    def test_passInCheckers(self):
        """
        L{UNIXPasswordDatabase} takes a list of functions to check for UNIX
        user information.
        """
        password = crypt.crypt("secret", "secret")
        userdb = UserDatabase()
        userdb.addUser("anybody", password, 1, 2, "foo", "/bar", "/bin/sh")
        checker = checkers.UNIXPasswordDatabase([userdb.getpwnam])
        self.assertLoggedIn(
            checker.requestAvatarId(UsernamePassword(b"anybody", b"secret")), b"anybody"
        )

    def test_verifyPassword(self):
        """
        If the encrypted password provided by the getpwnam function is valid
        (verified by the L{verifyCryptedPassword} function), we callback the
        C{requestAvatarId} L{Deferred} with the username.
        """

        def verifyCryptedPassword(crypted, pw):
            return crypted == pw

        def getpwnam(username):
            return [username, username]

        self.patch(checkers, "verifyCryptedPassword", verifyCryptedPassword)
        checker = checkers.UNIXPasswordDatabase([getpwnam])
        credential = UsernamePassword(b"username", b"username")
        self.assertLoggedIn(checker.requestAvatarId(credential), b"username")

    def test_failOnKeyError(self):
        """
        If the getpwnam function raises a KeyError, the login fails with an
        L{UnauthorizedLogin} exception.
        """

        def getpwnam(username):
            raise KeyError(username)

        checker = checkers.UNIXPasswordDatabase([getpwnam])
        credential = UsernamePassword(b"username", b"password")
        self.assertUnauthorizedLogin(checker.requestAvatarId(credential))

    def test_failOnBadPassword(self):
        """
        If the verifyCryptedPassword function doesn't verify the password, the
        login fails with an L{UnauthorizedLogin} exception.
        """

        def verifyCryptedPassword(crypted, pw):
            return False

        def getpwnam(username):
            return [username, b"password"]

        self.patch(checkers, "verifyCryptedPassword", verifyCryptedPassword)
        checker = checkers.UNIXPasswordDatabase([getpwnam])
        credential = UsernamePassword(b"username", b"password")
        self.assertUnauthorizedLogin(checker.requestAvatarId(credential))

    def test_loopThroughFunctions(self):
        """
        UNIXPasswordDatabase.requestAvatarId loops through each getpwnam
        function associated with it and returns a L{Deferred} which fires with
        the result of the first one which returns a value other than None.
        ones do not verify the password.
        """

        def verifyCryptedPassword(crypted, pw):
            return crypted == pw

        def getpwnam1(username):
            return [username, "not the password"]

        def getpwnam2(username):
            return [username, "password"]

        self.patch(checkers, "verifyCryptedPassword", verifyCryptedPassword)
        checker = checkers.UNIXPasswordDatabase([getpwnam1, getpwnam2])
        credential = UsernamePassword(b"username", b"password")
        self.assertLoggedIn(checker.requestAvatarId(credential), b"username")

    def test_failOnSpecial(self):
        """
        If the password returned by any function is C{""}, C{"x"}, or C{"*"} it
        is not compared against the supplied password.  Instead it is skipped.
        """
        pwd = UserDatabase()
        pwd.addUser("alice", "", 1, 2, "", "foo", "bar")
        pwd.addUser("bob", "x", 1, 2, "", "foo", "bar")
        pwd.addUser("carol", "*", 1, 2, "", "foo", "bar")
        self.patch(checkers, "pwd", pwd)

        checker = checkers.UNIXPasswordDatabase([checkers._pwdGetByName])
        cred = UsernamePassword(b"alice", b"")
        self.assertUnauthorizedLogin(checker.requestAvatarId(cred))

        cred = UsernamePassword(b"bob", b"x")
        self.assertUnauthorizedLogin(checker.requestAvatarId(cred))

        cred = UsernamePassword(b"carol", b"*")
        self.assertUnauthorizedLogin(checker.requestAvatarId(cred))


class AuthorizedKeyFileReaderTests(TestCase):
    """
    Tests for L{checkers.readAuthorizedKeyFile}
    """

    skip = dependencySkip

    def test_ignoresComments(self):
        """
        L{checkers.readAuthorizedKeyFile} does not attempt to turn comments
        into keys
        """
        fileobj = BytesIO(
            b"# this comment is ignored\n"
            b"this is not\n"
            b"# this is again\n"
            b"and this is not"
        )
        result = checkers.readAuthorizedKeyFile(fileobj, lambda x: x)
        self.assertEqual([b"this is not", b"and this is not"], list(result))

    def test_ignoresLeadingWhitespaceAndEmptyLines(self):
        """
        L{checkers.readAuthorizedKeyFile} ignores leading whitespace in
        lines, as well as empty lines
        """
        fileobj = BytesIO(
            b"""
                           # ignore
                           not ignored
                           """
        )
        result = checkers.readAuthorizedKeyFile(fileobj, parseKey=lambda x: x)
        self.assertEqual([b"not ignored"], list(result))

    def test_ignoresUnparsableKeys(self):
        """
        L{checkers.readAuthorizedKeyFile} does not raise an exception
        when a key fails to parse (raises a
        L{twisted.conch.ssh.keys.BadKeyError}), but rather just keeps going
        """

        def failOnSome(line):
            if line.startswith(b"f"):
                raise keys.BadKeyError("failed to parse")
            return line

        fileobj = BytesIO(b"failed key\ngood key")
        result = checkers.readAuthorizedKeyFile(fileobj, parseKey=failOnSome)
        self.assertEqual([b"good key"], list(result))


class InMemorySSHKeyDBTests(TestCase):
    """
    Tests for L{checkers.InMemorySSHKeyDB}
    """

    skip = dependencySkip

    def test_implementsInterface(self):
        """
        L{checkers.InMemorySSHKeyDB} implements
        L{checkers.IAuthorizedKeysDB}
        """
        keydb = checkers.InMemorySSHKeyDB({b"alice": [b"key"]})
        verifyObject(checkers.IAuthorizedKeysDB, keydb)

    def test_noKeysForUnauthorizedUser(self):
        """
        If the user is not in the mapping provided to
        L{checkers.InMemorySSHKeyDB}, an empty iterator is returned
        by L{checkers.InMemorySSHKeyDB.getAuthorizedKeys}
        """
        keydb = checkers.InMemorySSHKeyDB({b"alice": [b"keys"]})
        self.assertEqual([], list(keydb.getAuthorizedKeys(b"bob")))

    def test_allKeysForAuthorizedUser(self):
        """
        If the user is in the mapping provided to
        L{checkers.InMemorySSHKeyDB}, an iterator with all the keys
        is returned by L{checkers.InMemorySSHKeyDB.getAuthorizedKeys}
        """
        keydb = checkers.InMemorySSHKeyDB({b"alice": [b"a", b"b"]})
        self.assertEqual([b"a", b"b"], list(keydb.getAuthorizedKeys(b"alice")))


class UNIXAuthorizedKeysFilesTests(TestCase):
    """
    Tests for L{checkers.UNIXAuthorizedKeysFiles}.
    """

    skip = dependencySkip

    def setUp(self) -> None:
        self.path = FilePath(self.mktemp())
        assert isinstance(self.path.path, str)
        self.path.makedirs()

        self.userdb = UserDatabase()
        self.userdb.addUser(
            "alice",
            "password",
            1,
            2,
            "alice lastname",
            self.path.path,
            "/bin/shell",
        )

        self.sshDir = self.path.child(".ssh")
        self.sshDir.makedirs()
        authorizedKeys = self.sshDir.child("authorized_keys")
        authorizedKeys.setContent(b"key 1\nkey 2")

        self.expectedKeys = [b"key 1", b"key 2"]

    def test_implementsInterface(self):
        """
        L{checkers.UNIXAuthorizedKeysFiles} implements
        L{checkers.IAuthorizedKeysDB}.
        """
        keydb = checkers.UNIXAuthorizedKeysFiles(self.userdb)
        verifyObject(checkers.IAuthorizedKeysDB, keydb)

    def test_noKeysForUnauthorizedUser(self):
        """
        If the user is not in the user database provided to
        L{checkers.UNIXAuthorizedKeysFiles}, an empty iterator is returned
        by L{checkers.UNIXAuthorizedKeysFiles.getAuthorizedKeys}.
        """
        keydb = checkers.UNIXAuthorizedKeysFiles(self.userdb, parseKey=lambda x: x)
        self.assertEqual([], list(keydb.getAuthorizedKeys(b"bob")))

    def test_allKeysInAllAuthorizedFilesForAuthorizedUser(self):
        """
        If the user is in the user database provided to
        L{checkers.UNIXAuthorizedKeysFiles}, an iterator with all the keys in
        C{~/.ssh/authorized_keys} and C{~/.ssh/authorized_keys2} is returned
        by L{checkers.UNIXAuthorizedKeysFiles.getAuthorizedKeys}.
        """
        self.sshDir.child("authorized_keys2").setContent(b"key 3")
        keydb = checkers.UNIXAuthorizedKeysFiles(self.userdb, parseKey=lambda x: x)
        self.assertEqual(
            self.expectedKeys + [b"key 3"], list(keydb.getAuthorizedKeys(b"alice"))
        )

    def test_ignoresNonexistantFile(self):
        """
        L{checkers.UNIXAuthorizedKeysFiles.getAuthorizedKeys} returns only
        the keys in C{~/.ssh/authorized_keys} and C{~/.ssh/authorized_keys2}
        if they exist.
        """
        keydb = checkers.UNIXAuthorizedKeysFiles(self.userdb, parseKey=lambda x: x)
        self.assertEqual(self.expectedKeys, list(keydb.getAuthorizedKeys(b"alice")))

    def test_ignoresUnreadableFile(self):
        """
        L{checkers.UNIXAuthorizedKeysFiles.getAuthorizedKeys} returns only
        the keys in C{~/.ssh/authorized_keys} and C{~/.ssh/authorized_keys2}
        if they are readable.
        """
        self.sshDir.child("authorized_keys2").makedirs()
        keydb = checkers.UNIXAuthorizedKeysFiles(self.userdb, parseKey=lambda x: x)
        self.assertEqual(self.expectedKeys, list(keydb.getAuthorizedKeys(b"alice")))


_KeyDB = namedtuple("_KeyDB", ["getAuthorizedKeys"])


class _DummyException(Exception):
    """
    Fake exception to be used for testing.
    """

    pass


class SSHPublicKeyCheckerTests(TestCase):
    """
    Tests for L{checkers.SSHPublicKeyChecker}.
    """

    skip = dependencySkip

    def setUp(self):
        self.credentials = SSHPrivateKey(
            b"alice",
            b"ssh-rsa",
            keydata.publicRSA_openssh,
            b"foo",
            keys.Key.fromString(keydata.privateRSA_openssh).sign(b"foo"),
        )
        self.keydb = _KeyDB(lambda _: [keys.Key.fromString(keydata.publicRSA_openssh)])
        self.checker = checkers.SSHPublicKeyChecker(self.keydb)

    def test_credentialsWithoutSignature(self):
        """
        Calling L{checkers.SSHPublicKeyChecker.requestAvatarId} with
        credentials that do not have a signature fails with L{ValidPublicKey}.
        """
        self.credentials.signature = None
        self.failureResultOf(
            self.checker.requestAvatarId(self.credentials), ValidPublicKey
        )

    def test_credentialsWithBadKey(self):
        """
        Calling L{checkers.SSHPublicKeyChecker.requestAvatarId} with
        credentials that have a bad key fails with L{keys.BadKeyError}.
        """
        self.credentials.blob = b""
        self.failureResultOf(
            self.checker.requestAvatarId(self.credentials), keys.BadKeyError
        )

    def test_credentialsNoMatchingKey(self):
        """
        If L{checkers.IAuthorizedKeysDB.getAuthorizedKeys} returns no keys
        that match the credentials,
        L{checkers.SSHPublicKeyChecker.requestAvatarId} fails with
        L{UnauthorizedLogin}.
        """
        self.credentials.blob = keydata.publicDSA_openssh
        self.failureResultOf(
            self.checker.requestAvatarId(self.credentials), UnauthorizedLogin
        )

    def test_credentialsInvalidSignature(self):
        """
        Calling L{checkers.SSHPublicKeyChecker.requestAvatarId} with
        credentials that are incorrectly signed fails with
        L{UnauthorizedLogin}.
        """
        self.credentials.signature = keys.Key.fromString(
            keydata.privateDSA_openssh
        ).sign(b"foo")
        self.failureResultOf(
            self.checker.requestAvatarId(self.credentials), UnauthorizedLogin
        )

    def test_failureVerifyingKey(self):
        """
        If L{keys.Key.verify} raises an exception,
        L{checkers.SSHPublicKeyChecker.requestAvatarId} fails with
        L{UnauthorizedLogin}.
        """

        def fail(*args, **kwargs):
            raise _DummyException()

        self.patch(keys.Key, "verify", fail)

        self.failureResultOf(
            self.checker.requestAvatarId(self.credentials), UnauthorizedLogin
        )
        self.flushLoggedErrors(_DummyException)

    def test_usernameReturnedOnSuccess(self):
        """
        L{checker.SSHPublicKeyChecker.requestAvatarId}, if successful,
        callbacks with the username.
        """
        d = self.checker.requestAvatarId(self.credentials)
        self.assertEqual(b"alice", self.successResultOf(d))

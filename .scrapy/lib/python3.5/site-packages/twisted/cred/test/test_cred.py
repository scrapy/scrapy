# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.cred}, now with 30% more starch.
"""

from __future__ import absolute_import, division

from zope.interface import implementer, Interface

from binascii import hexlify, unhexlify

from twisted.trial import unittest
from twisted.python.compat import nativeString, networkString
from twisted.python import components
from twisted.internet import defer
from twisted.cred import checkers, credentials, portal, error

try:
    from crypt import crypt
except ImportError:
    crypt = None



class ITestable(Interface):
    """
    An interface for a theoretical protocol.
    """
    pass



class TestAvatar(object):
    """
    A test avatar.
    """
    def __init__(self, name):
        self.name = name
        self.loggedIn = False
        self.loggedOut = False


    def login(self):
        assert not self.loggedIn
        self.loggedIn = True


    def logout(self):
        self.loggedOut = True



@implementer(ITestable)
class Testable(components.Adapter):
    """
    A theoretical protocol for testing.
    """
    pass

components.registerAdapter(Testable, TestAvatar, ITestable)



class IDerivedCredentials(credentials.IUsernamePassword):
    pass



@implementer(IDerivedCredentials, ITestable)
class DerivedCredentials(object):

    def __init__(self, username, password):
        self.username = username
        self.password = password


    def checkPassword(self, password):
        return password == self.password



@implementer(portal.IRealm)
class TestRealm(object):
    """
    A basic test realm.
    """
    def __init__(self):
        self.avatars = {}


    def requestAvatar(self, avatarId, mind, *interfaces):
        if avatarId in self.avatars:
            avatar = self.avatars[avatarId]
        else:
            avatar = TestAvatar(avatarId)
            self.avatars[avatarId] = avatar
        avatar.login()
        return (interfaces[0], interfaces[0](avatar),
                avatar.logout)



class CredTests(unittest.TestCase):
    """
    Tests for the meat of L{twisted.cred} -- realms, portals, avatars, and
    checkers.
    """
    def setUp(self):
        self.realm = TestRealm()
        self.portal = portal.Portal(self.realm)
        self.checker = checkers.InMemoryUsernamePasswordDatabaseDontUse()
        self.checker.addUser(b"bob", b"hello")
        self.portal.registerChecker(self.checker)


    def test_listCheckers(self):
        """
        The checkers in a portal can check only certain types of credentials.
        Since this portal has
        L{checkers.InMemoryUsernamePasswordDatabaseDontUse} registered, it
        """
        expected = [credentials.IUsernamePassword,
                    credentials.IUsernameHashedPassword]
        got = self.portal.listCredentialsInterfaces()
        self.assertEqual(sorted(got), sorted(expected))


    def test_basicLogin(self):
        """
        Calling C{login} on a portal with correct credentials and an interface
        that the portal's realm supports works.
        """
        login = self.successResultOf(self.portal.login(
            credentials.UsernamePassword(b"bob", b"hello"), self, ITestable))
        iface, impl, logout = login

        # whitebox
        self.assertEqual(iface, ITestable)
        self.assertTrue(iface.providedBy(impl),
                        "%s does not implement %s" % (impl, iface))

        # greybox
        self.assertTrue(impl.original.loggedIn)
        self.assertTrue(not impl.original.loggedOut)
        logout()
        self.assertTrue(impl.original.loggedOut)


    def test_derivedInterface(self):
        """
        Logging in with correct derived credentials and an interface
        that the portal's realm supports works.
        """
        login = self.successResultOf(self.portal.login(
            DerivedCredentials(b"bob", b"hello"), self, ITestable))
        iface, impl, logout = login

        # whitebox
        self.assertEqual(iface, ITestable)
        self.assertTrue(iface.providedBy(impl),
                        "%s does not implement %s" % (impl, iface))

        # greybox
        self.assertTrue(impl.original.loggedIn)
        self.assertTrue(not impl.original.loggedOut)
        logout()
        self.assertTrue(impl.original.loggedOut)


    def test_failedLoginPassword(self):
        """
        Calling C{login} with incorrect credentials (in this case a wrong
        password) causes L{error.UnauthorizedLogin} to be raised.
        """
        login = self.failureResultOf(self.portal.login(
            credentials.UsernamePassword(b"bob", b"h3llo"), self, ITestable))
        self.assertTrue(login)
        self.assertEqual(error.UnauthorizedLogin, login.type)


    def test_failedLoginName(self):
        """
        Calling C{login} with incorrect credentials (in this case no known
        user) causes L{error.UnauthorizedLogin} to be raised.
        """
        login = self.failureResultOf(self.portal.login(
            credentials.UsernamePassword(b"jay", b"hello"), self, ITestable))
        self.assertTrue(login)
        self.assertEqual(error.UnauthorizedLogin, login.type)



class OnDiskDatabaseTests(unittest.TestCase):
    users = [
        (b'user1', b'pass1'),
        (b'user2', b'pass2'),
        (b'user3', b'pass3'),
    ]

    def setUp(self):
        self.dbfile = self.mktemp()
        with open(self.dbfile, 'wb') as f:
            for (u, p) in self.users:
                f.write(u + b":" + p + b"\n")


    def test_getUserNonexistentDatabase(self):
        """
        A missing db file will cause a permanent rejection of authorization
        attempts.
        """
        self.db = checkers.FilePasswordDB('test_thisbetternoteverexist.db')

        self.assertRaises(error.UnauthorizedLogin, self.db.getUser, 'user')


    def testUserLookup(self):
        self.db = checkers.FilePasswordDB(self.dbfile)
        for (u, p) in self.users:
            self.assertRaises(KeyError, self.db.getUser, u.upper())
            self.assertEqual(self.db.getUser(u), (u, p))


    def testCaseInSensitivity(self):
        self.db = checkers.FilePasswordDB(self.dbfile, caseSensitive=False)
        for (u, p) in self.users:
            self.assertEqual(self.db.getUser(u.upper()), (u, p))


    def testRequestAvatarId(self):
        self.db = checkers.FilePasswordDB(self.dbfile)
        creds = [credentials.UsernamePassword(u, p) for u, p in self.users]
        d = defer.gatherResults(
            [defer.maybeDeferred(self.db.requestAvatarId, c) for c in creds])
        d.addCallback(self.assertEqual, [u for u, p in self.users])
        return d


    def testRequestAvatarId_hashed(self):
        self.db = checkers.FilePasswordDB(self.dbfile)
        creds = [credentials.UsernameHashedPassword(u, p)
                 for u, p in self.users]
        d = defer.gatherResults(
            [defer.maybeDeferred(self.db.requestAvatarId, c) for c in creds])
        d.addCallback(self.assertEqual, [u for u, p in self.users])
        return d



class HashedPasswordOnDiskDatabaseTests(unittest.TestCase):
    users = [
        (b'user1', b'pass1'),
        (b'user2', b'pass2'),
        (b'user3', b'pass3'),
    ]

    def setUp(self):
        dbfile = self.mktemp()
        self.db = checkers.FilePasswordDB(dbfile, hash=self.hash)
        with open(dbfile, 'wb') as f:
            for (u, p) in self.users:
                f.write(u + b":" + self.hash(u, p, u[:2]) + b"\n")

        r = TestRealm()
        self.port = portal.Portal(r)
        self.port.registerChecker(self.db)


    def hash(self, u, p, s):
        return networkString(crypt(nativeString(p), nativeString(s)))


    def testGoodCredentials(self):
        goodCreds = [credentials.UsernamePassword(u, p) for u, p in self.users]
        d = defer.gatherResults([self.db.requestAvatarId(c)
                                 for c in goodCreds])
        d.addCallback(self.assertEqual, [u for u, p in self.users])
        return d


    def testGoodCredentials_login(self):
        goodCreds = [credentials.UsernamePassword(u, p) for u, p in self.users]
        d = defer.gatherResults([self.port.login(c, None, ITestable)
                                 for c in goodCreds])
        d.addCallback(lambda x: [a.original.name for i, a, l in x])
        d.addCallback(self.assertEqual, [u for u, p in self.users])
        return d


    def testBadCredentials(self):
        badCreds = [credentials.UsernamePassword(u, 'wrong password')
                    for u, p in self.users]
        d = defer.DeferredList([self.port.login(c, None, ITestable)
                                for c in badCreds], consumeErrors=True)
        d.addCallback(self._assertFailures, error.UnauthorizedLogin)
        return d


    def testHashedCredentials(self):
        hashedCreds = [credentials.UsernameHashedPassword(
            u, self.hash(None, p, u[:2])) for u, p in self.users]
        d = defer.DeferredList([self.port.login(c, None, ITestable)
                                for c in hashedCreds], consumeErrors=True)
        d.addCallback(self._assertFailures, error.UnhandledCredentials)
        return d


    def _assertFailures(self, failures, *expectedFailures):
        for flag, failure in failures:
            self.assertEqual(flag, defer.FAILURE)
            failure.trap(*expectedFailures)
        return None

    if crypt is None:
        skip = "crypt module not available"



class CheckersMixin(object):
    """
    L{unittest.TestCase} mixin for testing that some checkers accept
    and deny specified credentials.

    Subclasses must provide
    - C{getCheckers} which returns a sequence of
      L{checkers.ICredentialChecker}
    - C{getGoodCredentials} which returns a list of 2-tuples of
      credential to check and avaterId to expect.
    - C{getBadCredentials} which returns a list of credentials
      which are expected to be unauthorized.
    """

    @defer.inlineCallbacks
    def test_positive(self):
        """
        The given credentials are accepted by all the checkers, and give
        the expected C{avatarID}s
        """
        for chk in self.getCheckers():
            for (cred, avatarId) in self.getGoodCredentials():
                r = yield chk.requestAvatarId(cred)
                self.assertEqual(r, avatarId)


    @defer.inlineCallbacks
    def test_negative(self):
        """
        The given credentials are rejected by all the checkers.
        """
        for chk in self.getCheckers():
            for cred in self.getBadCredentials():
                d = chk.requestAvatarId(cred)
                yield self.assertFailure(d, error.UnauthorizedLogin)



class HashlessFilePasswordDBMixin(object):
    credClass = credentials.UsernamePassword
    diskHash = None
    networkHash = staticmethod(lambda x: x)

    _validCredentials = [
        (b'user1', b'password1'),
        (b'user2', b'password2'),
        (b'user3', b'password3')]


    def getGoodCredentials(self):
        for u, p in self._validCredentials:
            yield self.credClass(u, self.networkHash(p)), u


    def getBadCredentials(self):
        for u, p in [(b'user1', b'password3'),
                     (b'user2', b'password1'),
                     (b'bloof', b'blarf')]:
            yield self.credClass(u, self.networkHash(p))


    def getCheckers(self):
        diskHash = self.diskHash or (lambda x: x)
        hashCheck = self.diskHash and (lambda username, password,
                                       stored: self.diskHash(password))

        for cache in True, False:
            fn = self.mktemp()
            with open(fn, 'wb') as fObj:
                for u, p in self._validCredentials:
                    fObj.write(u + b":" + diskHash(p) + b"\n")
            yield checkers.FilePasswordDB(fn, cache=cache, hash=hashCheck)

            fn = self.mktemp()
            with open(fn, 'wb') as fObj:
                for u, p in self._validCredentials:
                    fObj.write(diskHash(p) + b' dingle dongle ' + u + b'\n')
            yield checkers.FilePasswordDB(fn, b' ', 3, 0,
                                          cache=cache, hash=hashCheck)

            fn = self.mktemp()
            with open(fn, 'wb') as fObj:
                for u, p in self._validCredentials:
                    fObj.write(b'zip,zap,' + u.title() + b',zup,'\
                               + diskHash(p) + b'\n',)
            yield checkers.FilePasswordDB(fn, b',', 2, 4, False,
                                          cache=cache, hash=hashCheck)



class LocallyHashedFilePasswordDBMixin(HashlessFilePasswordDBMixin):
    diskHash = staticmethod(lambda x: hexlify(x))



class NetworkHashedFilePasswordDBMixin(HashlessFilePasswordDBMixin):
    networkHash = staticmethod(lambda x: hexlify(x))

    class credClass(credentials.UsernameHashedPassword):
        def checkPassword(self, password):
            return unhexlify(self.hashed) == password



class HashlessFilePasswordDBCheckerTests(HashlessFilePasswordDBMixin,
                                         CheckersMixin, unittest.TestCase):
    pass



class LocallyHashedFilePasswordDBCheckerTests(LocallyHashedFilePasswordDBMixin,
                                              CheckersMixin,
                                              unittest.TestCase):
    pass



class NetworkHashedFilePasswordDBCheckerTests(NetworkHashedFilePasswordDBMixin,
                                              CheckersMixin,
                                              unittest.TestCase):
    pass

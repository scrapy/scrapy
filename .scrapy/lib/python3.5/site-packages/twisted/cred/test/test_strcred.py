# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.cred.strcred}.
"""

from __future__ import absolute_import, division

import os

from twisted import plugin
from twisted.trial import unittest
from twisted.cred import credentials, checkers, error, strcred
from twisted.plugins import cred_file, cred_anonymous
from twisted.python import usage, compat
from twisted.python.filepath import FilePath
from twisted.python.fakepwd import UserDatabase
from twisted.python.reflect import requireModule

if compat._PY3:
    from io import StringIO
else:
    from io import BytesIO as StringIO

try:
    import crypt
except ImportError:
    crypt = None

try:
    import pwd
except ImportError:
    pwd = None

try:
    import spwd
except ImportError:
    spwd = None



def getInvalidAuthType():
    """
    Helper method to produce an auth type that doesn't exist.
    """
    invalidAuthType = 'ThisPluginDoesNotExist'
    while (invalidAuthType in
           [factory.authType for factory in strcred.findCheckerFactories()]):
        invalidAuthType += '_'
    return invalidAuthType



class PublicAPITests(unittest.TestCase):

    def test_emptyDescription(self):
        """
        Test that the description string cannot be empty.
        """
        iat = getInvalidAuthType()
        self.assertRaises(strcred.InvalidAuthType, strcred.makeChecker, iat)
        self.assertRaises(
            strcred.InvalidAuthType, strcred.findCheckerFactory, iat)


    def test_invalidAuthType(self):
        """
        Test that an unrecognized auth type raises an exception.
        """
        iat = getInvalidAuthType()
        self.assertRaises(strcred.InvalidAuthType, strcred.makeChecker, iat)
        self.assertRaises(
            strcred.InvalidAuthType, strcred.findCheckerFactory, iat)



class StrcredFunctionsTests(unittest.TestCase):

    def test_findCheckerFactories(self):
        """
        Test that findCheckerFactories returns all available plugins.
        """
        availablePlugins = list(strcred.findCheckerFactories())
        for plg in plugin.getPlugins(strcred.ICheckerFactory):
            self.assertIn(plg, availablePlugins)


    def test_findCheckerFactory(self):
        """
        Test that findCheckerFactory returns the first plugin
        available for a given authentication type.
        """
        self.assertIdentical(strcred.findCheckerFactory('file'),
                             cred_file.theFileCheckerFactory)



class MemoryCheckerTests(unittest.TestCase):

    def setUp(self):
        self.admin = credentials.UsernamePassword('admin', 'asdf')
        self.alice = credentials.UsernamePassword('alice', 'foo')
        self.badPass = credentials.UsernamePassword('alice', 'foobar')
        self.badUser = credentials.UsernamePassword('x', 'yz')
        self.checker = strcred.makeChecker('memory:admin:asdf:alice:foo')


    def test_isChecker(self):
        """
        Verifies that strcred.makeChecker('memory') returns an object
        that implements the L{ICredentialsChecker} interface.
        """
        self.assertTrue(checkers.ICredentialsChecker.providedBy(self.checker))
        self.assertIn(credentials.IUsernamePassword,
                      self.checker.credentialInterfaces)


    def test_badFormatArgString(self):
        """
        Test that an argument string which does not contain user:pass
        pairs (i.e., an odd number of ':' characters) raises an exception.
        """
        self.assertRaises(strcred.InvalidAuthArgumentString,
                          strcred.makeChecker, 'memory:a:b:c')


    def test_memoryCheckerSucceeds(self):
        """
        Test that the checker works with valid credentials.
        """
        def _gotAvatar(username):
            self.assertEqual(username, self.admin.username)
        return (self.checker
                .requestAvatarId(self.admin)
                .addCallback(_gotAvatar))


    def test_memoryCheckerFailsUsername(self):
        """
        Test that the checker fails with an invalid username.
        """
        return self.assertFailure(self.checker.requestAvatarId(self.badUser),
                                  error.UnauthorizedLogin)


    def test_memoryCheckerFailsPassword(self):
        """
        Test that the checker fails with an invalid password.
        """
        return self.assertFailure(self.checker.requestAvatarId(self.badPass),
                                  error.UnauthorizedLogin)



class AnonymousCheckerTests(unittest.TestCase):

    def test_isChecker(self):
        """
        Verifies that strcred.makeChecker('anonymous') returns an object
        that implements the L{ICredentialsChecker} interface.
        """
        checker = strcred.makeChecker('anonymous')
        self.assertTrue(checkers.ICredentialsChecker.providedBy(checker))
        self.assertIn(credentials.IAnonymous, checker.credentialInterfaces)


    def testAnonymousAccessSucceeds(self):
        """
        Test that we can log in anonymously using this checker.
        """
        checker = strcred.makeChecker('anonymous')
        request = checker.requestAvatarId(credentials.Anonymous())
        def _gotAvatar(avatar):
            self.assertIdentical(checkers.ANONYMOUS, avatar)
        return request.addCallback(_gotAvatar)



class UnixCheckerTests(unittest.TestCase):
    users = {
        'admin': 'asdf',
        'alice': 'foo',
        }


    def _spwd(self, username):
        return (username, crypt.crypt(self.users[username], 'F/'),
                0, 0, 99999, 7, -1, -1, -1)


    def setUp(self):
        self.admin = credentials.UsernamePassword('admin', 'asdf')
        self.alice = credentials.UsernamePassword('alice', 'foo')
        self.badPass = credentials.UsernamePassword('alice', 'foobar')
        self.badUser = credentials.UsernamePassword('x', 'yz')
        self.checker = strcred.makeChecker('unix')

        # Hack around the pwd and spwd modules, since we can't really
        # go about reading your /etc/passwd or /etc/shadow files
        if pwd:
            database = UserDatabase()
            for username, password in self.users.items():
                database.addUser(
                    username, crypt.crypt(password, 'F/'),
                    1000, 1000, username, '/home/' + username, '/bin/sh')
            self.patch(pwd, 'getpwnam', database.getpwnam)
        if spwd:
            self._spwd_getspnam = spwd.getspnam
            spwd.getspnam = self._spwd


    def tearDown(self):
        if spwd:
            spwd.getspnam = self._spwd_getspnam


    def test_isChecker(self):
        """
        Verifies that strcred.makeChecker('unix') returns an object
        that implements the L{ICredentialsChecker} interface.
        """
        self.assertTrue(checkers.ICredentialsChecker.providedBy(self.checker))
        self.assertIn(credentials.IUsernamePassword,
                      self.checker.credentialInterfaces)


    def test_unixCheckerSucceeds(self):
        """
        Test that the checker works with valid credentials.
        """
        def _gotAvatar(username):
            self.assertEqual(username, self.admin.username)
        return (self.checker
                .requestAvatarId(self.admin)
                .addCallback(_gotAvatar))


    def test_unixCheckerFailsUsername(self):
        """
        Test that the checker fails with an invalid username.
        """
        return self.assertFailure(self.checker.requestAvatarId(self.badUser),
                                  error.UnauthorizedLogin)


    def test_unixCheckerFailsPassword(self):
        """
        Test that the checker fails with an invalid password.
        """
        return self.assertFailure(self.checker.requestAvatarId(self.badPass),
                                  error.UnauthorizedLogin)


    if None in (pwd, spwd, crypt):
        availability = []
        for module, name in ((pwd, "pwd"), (spwd, "spwd"), (crypt, "crypt")):
            if module is None:
                availability += [name]
        for method in (test_unixCheckerSucceeds,
                       test_unixCheckerFailsUsername,
                       test_unixCheckerFailsPassword):
            method.skip = ("Required module(s) are unavailable: " +
                           ", ".join(availability))



class FileDBCheckerTests(unittest.TestCase):
    """
    Test for the --auth=file:... file checker.
    """

    def setUp(self):
        self.admin = credentials.UsernamePassword(b'admin', b'asdf')
        self.alice = credentials.UsernamePassword(b'alice', b'foo')
        self.badPass = credentials.UsernamePassword(b'alice', b'foobar')
        self.badUser = credentials.UsernamePassword(b'x', b'yz')
        self.filename = self.mktemp()
        FilePath(self.filename).setContent(b'admin:asdf\nalice:foo\n')
        self.checker = strcred.makeChecker('file:' + self.filename)


    def _fakeFilename(self):
        filename = '/DoesNotExist'
        while os.path.exists(filename):
            filename += '_'
        return filename


    def test_isChecker(self):
        """
        Verifies that strcred.makeChecker('memory') returns an object
        that implements the L{ICredentialsChecker} interface.
        """
        self.assertTrue(checkers.ICredentialsChecker.providedBy(self.checker))
        self.assertIn(credentials.IUsernamePassword,
                      self.checker.credentialInterfaces)


    def test_fileCheckerSucceeds(self):
        """
        Test that the checker works with valid credentials.
        """
        def _gotAvatar(username):
            self.assertEqual(username, self.admin.username)
        return (self.checker
                .requestAvatarId(self.admin)
                .addCallback(_gotAvatar))


    def test_fileCheckerFailsUsername(self):
        """
        Test that the checker fails with an invalid username.
        """
        return self.assertFailure(self.checker.requestAvatarId(self.badUser),
                                  error.UnauthorizedLogin)


    def test_fileCheckerFailsPassword(self):
        """
        Test that the checker fails with an invalid password.
        """
        return self.assertFailure(self.checker.requestAvatarId(self.badPass),
                                  error.UnauthorizedLogin)


    def test_failsWithEmptyFilename(self):
        """
        Test that an empty filename raises an error.
        """
        self.assertRaises(ValueError, strcred.makeChecker, 'file')
        self.assertRaises(ValueError, strcred.makeChecker, 'file:')


    def test_warnWithBadFilename(self):
        """
        When the file auth plugin is given a file that doesn't exist, it
        should produce a warning.
        """
        oldOutput = cred_file.theFileCheckerFactory.errorOutput
        newOutput = StringIO()
        cred_file.theFileCheckerFactory.errorOutput = newOutput
        strcred.makeChecker('file:' + self._fakeFilename())
        cred_file.theFileCheckerFactory.errorOutput = oldOutput
        self.assertIn(cred_file.invalidFileWarning, newOutput.getvalue())



class SSHCheckerTests(unittest.TestCase):
    """
    Tests for the --auth=sshkey:... checker.  The majority of the tests for the
    ssh public key database checker are in
    L{twisted.conch.test.test_checkers.SSHPublicKeyCheckerTestCase}.
    """

    skip = None

    if requireModule('cryptography') is None:
        skip = 'cryptography is not available'

    if requireModule('pyasn1') is None:
        skip = 'pyasn1 is not available'


    def test_isChecker(self):
        """
        Verifies that strcred.makeChecker('sshkey') returns an object
        that implements the L{ICredentialsChecker} interface.
        """
        sshChecker = strcred.makeChecker('sshkey')
        self.assertTrue(checkers.ICredentialsChecker.providedBy(sshChecker))
        self.assertIn(
            credentials.ISSHPrivateKey, sshChecker.credentialInterfaces)



class DummyOptions(usage.Options, strcred.AuthOptionMixin):
    """
    Simple options for testing L{strcred.AuthOptionMixin}.
    """



class CheckerOptionsTests(unittest.TestCase):

    def test_createsList(self):
        """
        Test that the --auth command line creates a list in the
        Options instance and appends values to it.
        """
        options = DummyOptions()
        options.parseOptions(['--auth', 'memory'])
        self.assertEqual(len(options['credCheckers']), 1)
        options = DummyOptions()
        options.parseOptions(['--auth', 'memory', '--auth', 'memory'])
        self.assertEqual(len(options['credCheckers']), 2)


    def test_invalidAuthError(self):
        """
        Test that the --auth command line raises an exception when it
        gets a parameter it doesn't understand.
        """
        options = DummyOptions()
        # If someone adds a 'ThisPluginDoesNotExist' then this unit
        # test should still run.
        invalidParameter = getInvalidAuthType()
        self.assertRaises(
            usage.UsageError,
            options.parseOptions, ['--auth', invalidParameter])
        self.assertRaises(
            usage.UsageError,
            options.parseOptions, ['--help-auth-type', invalidParameter])


    def test_createsDictionary(self):
        """
        Test that the --auth command line creates a dictionary
        mapping supported interfaces to the list of credentials
        checkers that support it.
        """
        options = DummyOptions()
        options.parseOptions(['--auth', 'memory', '--auth', 'anonymous'])
        chd = options['credInterfaces']
        self.assertEqual(len(chd[credentials.IAnonymous]), 1)
        self.assertEqual(len(chd[credentials.IUsernamePassword]), 1)
        chdAnonymous = chd[credentials.IAnonymous][0]
        chdUserPass = chd[credentials.IUsernamePassword][0]
        self.assertTrue(checkers.ICredentialsChecker.providedBy(chdAnonymous))
        self.assertTrue(checkers.ICredentialsChecker.providedBy(chdUserPass))
        self.assertIn(credentials.IAnonymous,
                      chdAnonymous.credentialInterfaces)
        self.assertIn(credentials.IUsernamePassword,
                      chdUserPass.credentialInterfaces)


    def test_credInterfacesProvidesLists(self):
        """
        Test that when two --auth arguments are passed along which
        support the same interface, a list with both is created.
        """
        options = DummyOptions()
        options.parseOptions(['--auth', 'memory', '--auth', 'unix'])
        self.assertEqual(
            options['credCheckers'],
            options['credInterfaces'][credentials.IUsernamePassword])


    def test_listDoesNotDisplayDuplicates(self):
        """
        Test that the list for --help-auth does not duplicate items.
        """
        authTypes = []
        options = DummyOptions()
        for cf in options._checkerFactoriesForOptHelpAuth():
            self.assertNotIn(cf.authType, authTypes)
            authTypes.append(cf.authType)


    def test_displaysListCorrectly(self):
        """
        Test that the --help-auth argument correctly displays all
        available authentication plugins, then exits.
        """
        newStdout = StringIO()
        options = DummyOptions()
        options.authOutput = newStdout
        self.assertRaises(SystemExit, options.parseOptions, ['--help-auth'])
        for checkerFactory in strcred.findCheckerFactories():
            self.assertIn(checkerFactory.authType, newStdout.getvalue())


    def test_displaysHelpCorrectly(self):
        """
        Test that the --help-auth-for argument will correctly display
        the help file for a particular authentication plugin.
        """
        newStdout = StringIO()
        options = DummyOptions()
        options.authOutput = newStdout
        self.assertRaises(
            SystemExit, options.parseOptions, ['--help-auth-type', 'file'])
        for line in cred_file.theFileCheckerFactory.authHelp:
            if line.strip():
                self.assertIn(line.strip(), newStdout.getvalue())


    def test_unexpectedException(self):
        """
        When the checker specified by --auth raises an unexpected error, it
        should be caught and re-raised within a L{usage.UsageError}.
        """
        options = DummyOptions()
        err = self.assertRaises(usage.UsageError, options.parseOptions,
                                ['--auth', 'file'])
        self.assertEqual(str(err),
                          "Unexpected error: 'file' requires a filename")



class OptionsForUsernamePassword(usage.Options, strcred.AuthOptionMixin):
    supportedInterfaces = (credentials.IUsernamePassword,)



class OptionsForUsernameHashedPassword(usage.Options, strcred.AuthOptionMixin):
    supportedInterfaces = (credentials.IUsernameHashedPassword,)



class OptionsSupportsAllInterfaces(usage.Options, strcred.AuthOptionMixin):
    supportedInterfaces = None



class OptionsSupportsNoInterfaces(usage.Options, strcred.AuthOptionMixin):
    supportedInterfaces = []



class LimitingInterfacesTests(unittest.TestCase):
    """
    Tests functionality that allows an application to limit the
    credential interfaces it can support. For the purposes of this
    test, we use IUsernameHashedPassword, although this will never
    really be used by the command line.

    (I have, to date, not thought of a half-decent way for a user to
    specify a hash algorithm via the command-line. Nor do I think it's
    very useful.)

    I should note that, at first, this test is counter-intuitive,
    because we're using the checker with a pre-defined hash function
    as the 'bad' checker. See the documentation for
    L{twisted.cred.checkers.FilePasswordDB.hash} for more details.
    """

    def setUp(self):
        self.filename = self.mktemp()
        with open(self.filename, 'wb') as f:
            f.write(b'admin:asdf\nalice:foo\n')
        self.goodChecker = checkers.FilePasswordDB(self.filename)
        self.badChecker = checkers.FilePasswordDB(
            self.filename, hash=self._hash)
        self.anonChecker = checkers.AllowAnonymousAccess()


    def _hash(self, networkUsername, networkPassword, storedPassword):
        """
        A dumb hash that doesn't really do anything.
        """
        return networkPassword


    def test_supportsInterface(self):
        """
        Test that the supportsInterface method behaves appropriately.
        """
        options = OptionsForUsernamePassword()
        self.assertTrue(
            options.supportsInterface(credentials.IUsernamePassword))
        self.assertFalse(
            options.supportsInterface(credentials.IAnonymous))
        self.assertRaises(
            strcred.UnsupportedInterfaces, options.addChecker,
            self.anonChecker)


    def test_supportsAllInterfaces(self):
        """
        Test that the supportsInterface method behaves appropriately
        when the supportedInterfaces attribute is None.
        """
        options = OptionsSupportsAllInterfaces()
        self.assertTrue(
            options.supportsInterface(credentials.IUsernamePassword))
        self.assertTrue(
            options.supportsInterface(credentials.IAnonymous))


    def test_supportsCheckerFactory(self):
        """
        Test that the supportsCheckerFactory method behaves appropriately.
        """
        options = OptionsForUsernamePassword()
        fileCF = cred_file.theFileCheckerFactory
        anonCF = cred_anonymous.theAnonymousCheckerFactory
        self.assertTrue(options.supportsCheckerFactory(fileCF))
        self.assertFalse(options.supportsCheckerFactory(anonCF))


    def test_canAddSupportedChecker(self):
        """
        Test that when addChecker is called with a checker that
        implements at least one of the interfaces our application
        supports, it is successful.
        """
        options = OptionsForUsernamePassword()
        options.addChecker(self.goodChecker)
        iface = options.supportedInterfaces[0]
        # Test that we did get IUsernamePassword
        self.assertIdentical(
            options['credInterfaces'][iface][0], self.goodChecker)
        self.assertIdentical(options['credCheckers'][0], self.goodChecker)
        # Test that we didn't get IUsernameHashedPassword
        self.assertEqual(len(options['credInterfaces'][iface]), 1)
        self.assertEqual(len(options['credCheckers']), 1)


    def test_failOnAddingUnsupportedChecker(self):
        """
        Test that when addChecker is called with a checker that does
        not implement any supported interfaces, it fails.
        """
        options = OptionsForUsernameHashedPassword()
        self.assertRaises(strcred.UnsupportedInterfaces,
                          options.addChecker, self.badChecker)


    def test_unsupportedInterfaceError(self):
        """
        Test that the --auth command line raises an exception when it
        gets a checker we don't support.
        """
        options = OptionsSupportsNoInterfaces()
        authType = cred_anonymous.theAnonymousCheckerFactory.authType
        self.assertRaises(
            usage.UsageError,
            options.parseOptions, ['--auth', authType])


    def test_helpAuthLimitsOutput(self):
        """
        Test that --help-auth will only list checkers that purport to
        supply at least one of the credential interfaces our
        application can use.
        """
        options = OptionsForUsernamePassword()
        for factory in options._checkerFactoriesForOptHelpAuth():
            invalid = True
            for interface in factory.credentialInterfaces:
                if options.supportsInterface(interface):
                    invalid = False
            if invalid:
                raise strcred.UnsupportedInterfaces()


    def test_helpAuthTypeLimitsOutput(self):
        """
        Test that --help-auth-type will display a warning if you get
        help for an authType that does not supply at least one of the
        credential interfaces our application can use.
        """
        options = OptionsForUsernamePassword()
        # Find an interface that we can use for our test
        invalidFactory = None
        for factory in strcred.findCheckerFactories():
            if not options.supportsCheckerFactory(factory):
                invalidFactory = factory
                break
        self.assertNotIdentical(invalidFactory, None)
        # Capture output and make sure the warning is there
        newStdout = StringIO()
        options.authOutput = newStdout
        self.assertRaises(SystemExit, options.parseOptions,
                          ['--help-auth-type', 'anonymous'])
        self.assertIn(strcred.notSupportedWarning, newStdout.getvalue())


__all__ = [
    "CheckerOptionsTests", "FileDBCheckerTests", "LimitingInterfacesTests",
    "SSHCheckerTests", "UnixCheckerTests", "AnonymousCheckerTests",
    "MemoryCheckerTests", "StrcredFunctionsTests", "PublicAPITests"
]

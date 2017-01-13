# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for the implementation of the ssh-userauth service.

Maintainer: Paul Swartz
"""

from __future__ import absolute_import, division

from zope.interface import implementer

from twisted.cred.checkers import ICredentialsChecker
from twisted.cred.credentials import IUsernamePassword, ISSHPrivateKey
from twisted.cred.credentials import IAnonymous
from twisted.cred.error import UnauthorizedLogin
from twisted.cred.portal import IRealm, Portal
from twisted.conch.error import ConchError, ValidPublicKey
from twisted.internet import defer, task
from twisted.protocols import loopback
from twisted.python.reflect import requireModule
from twisted.trial import unittest
from twisted.python.compat import _bytesChr as chr

if requireModule('cryptography') and requireModule('pyasn1'):
    from twisted.conch.ssh.common import NS
    from twisted.conch.checkers import SSHProtocolChecker
    from twisted.conch.ssh import keys, userauth, transport
    from twisted.conch.test import keydata
else:
    keys = None


    class transport:
        class SSHTransportBase:
            """
            A stub class so that later class definitions won't die.
            """

    class userauth:
        class SSHUserAuthClient:
            """
            A stub class so that later class definitions won't die.
            """



class ClientUserAuth(userauth.SSHUserAuthClient):
    """
    A mock user auth client.
    """

    def getPublicKey(self):
        """
        If this is the first time we've been called, return a blob for
        the DSA key.  Otherwise, return a blob
        for the RSA key.
        """
        if self.lastPublicKey:
            return keys.Key.fromString(keydata.publicRSA_openssh)
        else:
            return defer.succeed(
                keys.Key.fromString(keydata.publicDSA_openssh))


    def getPrivateKey(self):
        """
        Return the private key object for the RSA key.
        """
        return defer.succeed(keys.Key.fromString(keydata.privateRSA_openssh))


    def getPassword(self, prompt=None):
        """
        Return 'foo' as the password.
        """
        return defer.succeed(b'foo')


    def getGenericAnswers(self, name, information, answers):
        """
        Return 'foo' as the answer to two questions.
        """
        return defer.succeed((b'foo', b'foo'))



class OldClientAuth(userauth.SSHUserAuthClient):
    """
    The old SSHUserAuthClient returned a cryptography key object from
    getPrivateKey() and a string from getPublicKey
    """

    def getPrivateKey(self):
        return defer.succeed(keys.Key.fromString(
            keydata.privateRSA_openssh).keyObject)


    def getPublicKey(self):
        return keys.Key.fromString(keydata.publicRSA_openssh).blob()



class ClientAuthWithoutPrivateKey(userauth.SSHUserAuthClient):
    """
    This client doesn't have a private key, but it does have a public key.
    """

    def getPrivateKey(self):
        return


    def getPublicKey(self):
        return keys.Key.fromString(keydata.publicRSA_openssh)



class FakeTransport(transport.SSHTransportBase):
    """
    L{userauth.SSHUserAuthServer} expects an SSH transport which has a factory
    attribute which has a portal attribute. Because the portal is important for
    testing authentication, we need to be able to provide an interesting portal
    object to the L{SSHUserAuthServer}.

    In addition, we want to be able to capture any packets sent over the
    transport.

    @ivar packets: a list of 2-tuples: (messageType, data).  Each 2-tuple is
        a sent packet.
    @type packets: C{list}
    @param lostConnecion: True if loseConnection has been called on us.
    @type lostConnection: L{bool}
    """

    class Service(object):
        """
        A mock service, representing the other service offered by the server.
        """
        name = b'nancy'


        def serviceStarted(self):
            pass


    class Factory(object):
        """
        A mock factory, representing the factory that spawned this user auth
        service.
        """

        def getService(self, transport, service):
            """
            Return our fake service.
            """
            if service == b'none':
                return FakeTransport.Service


    def __init__(self, portal):
        self.factory = self.Factory()
        self.factory.portal = portal
        self.lostConnection = False
        self.transport = self
        self.packets = []


    def sendPacket(self, messageType, message):
        """
        Record the packet sent by the service.
        """
        self.packets.append((messageType, message))


    def isEncrypted(self, direction):
        """
        Pretend that this transport encrypts traffic in both directions. The
        SSHUserAuthServer disables password authentication if the transport
        isn't encrypted.
        """
        return True


    def loseConnection(self):
        self.lostConnection = True



@implementer(IRealm)
class Realm(object):
    """
    A mock realm for testing L{userauth.SSHUserAuthServer}.

    This realm is not actually used in the course of testing, so it returns the
    simplest thing that could possibly work.
    """

    def requestAvatar(self, avatarId, mind, *interfaces):
        return defer.succeed((interfaces[0], None, lambda: None))



@implementer(ICredentialsChecker)
class PasswordChecker(object):
    """
    A very simple username/password checker which authenticates anyone whose
    password matches their username and rejects all others.
    """
    credentialInterfaces = (IUsernamePassword,)

    def requestAvatarId(self, creds):
        if creds.username == creds.password:
            return defer.succeed(creds.username)
        return defer.fail(UnauthorizedLogin("Invalid username/password pair"))



@implementer(ICredentialsChecker)
class PrivateKeyChecker(object):
    """
    A very simple public key checker which authenticates anyone whose
    public/private keypair is the same keydata.public/privateRSA_openssh.
    """
    credentialInterfaces = (ISSHPrivateKey,)

    def requestAvatarId(self, creds):
        if creds.blob == keys.Key.fromString(keydata.publicRSA_openssh).blob():
            if creds.signature is not None:
                obj = keys.Key.fromString(creds.blob)
                if obj.verify(creds.signature, creds.sigData):
                    return creds.username
            else:
                raise ValidPublicKey()
        raise UnauthorizedLogin()



@implementer(ICredentialsChecker)
class AnonymousChecker(object):
    """
    A simple checker which isn't supported by L{SSHUserAuthServer}.
    """
    credentialInterfaces = (IAnonymous,)



class SSHUserAuthServerTests(unittest.TestCase):
    """
    Tests for SSHUserAuthServer.
    """

    if keys is None:
        skip = "cannot run without cryptography"


    def setUp(self):
        self.realm = Realm()
        self.portal = Portal(self.realm)
        self.portal.registerChecker(PasswordChecker())
        self.portal.registerChecker(PrivateKeyChecker())
        self.authServer = userauth.SSHUserAuthServer()
        self.authServer.transport = FakeTransport(self.portal)
        self.authServer.serviceStarted()
        self.authServer.supportedAuthentications.sort() # give a consistent
                                                        # order


    def tearDown(self):
        self.authServer.serviceStopped()
        self.authServer = None


    def _checkFailed(self, ignored):
        """
        Check that the authentication has failed.
        """
        self.assertEqual(self.authServer.transport.packets[-1],
                (userauth.MSG_USERAUTH_FAILURE,
                NS(b'password,publickey') + b'\x00'))


    def test_noneAuthentication(self):
        """
        A client may request a list of authentication 'method name' values
        that may continue by using the "none" authentication 'method name'.

        See RFC 4252 Section 5.2.
        """
        d = self.authServer.ssh_USERAUTH_REQUEST(NS(b'foo') + NS(b'service') +
                                                 NS(b'none'))
        return d.addCallback(self._checkFailed)


    def test_successfulPasswordAuthentication(self):
        """
        When provided with correct password authentication information, the
        server should respond by sending a MSG_USERAUTH_SUCCESS message with
        no other data.

        See RFC 4252, Section 5.1.
        """
        packet = b''.join([NS(b'foo'), NS(b'none'), NS(b'password'), chr(0),
                           NS(b'foo')])
        d = self.authServer.ssh_USERAUTH_REQUEST(packet)
        def check(ignored):
            self.assertEqual(
                self.authServer.transport.packets,
                [(userauth.MSG_USERAUTH_SUCCESS, b'')])
        return d.addCallback(check)


    def test_failedPasswordAuthentication(self):
        """
        When provided with invalid authentication details, the server should
        respond by sending a MSG_USERAUTH_FAILURE message which states whether
        the authentication was partially successful, and provides other, open
        options for authentication.

        See RFC 4252, Section 5.1.
        """
        # packet = username, next_service, authentication type, FALSE, password
        packet = b''.join([NS(b'foo'), NS(b'none'), NS(b'password'), chr(0),
                           NS(b'bar')])
        self.authServer.clock = task.Clock()
        d = self.authServer.ssh_USERAUTH_REQUEST(packet)
        self.assertEqual(self.authServer.transport.packets, [])
        self.authServer.clock.advance(2)
        return d.addCallback(self._checkFailed)


    def test_successfulPrivateKeyAuthentication(self):
        """
        Test that private key authentication completes successfully,
        """
        blob = keys.Key.fromString(keydata.publicRSA_openssh).blob()
        obj = keys.Key.fromString(keydata.privateRSA_openssh)
        packet = (NS(b'foo') + NS(b'none') + NS(b'publickey') + b'\xff'
                + NS(obj.sshType()) + NS(blob))
        self.authServer.transport.sessionID = b'test'
        signature = obj.sign(NS(b'test') + chr(userauth.MSG_USERAUTH_REQUEST)
                + packet)
        packet += NS(signature)
        d = self.authServer.ssh_USERAUTH_REQUEST(packet)
        def check(ignored):
            self.assertEqual(self.authServer.transport.packets,
                    [(userauth.MSG_USERAUTH_SUCCESS, b'')])
        return d.addCallback(check)


    def test_requestRaisesConchError(self):
        """
        ssh_USERAUTH_REQUEST should raise a ConchError if tryAuth returns
        None. Added to catch a bug noticed by pyflakes.
        """
        d = defer.Deferred()

        def mockCbFinishedAuth(self, ignored):
            self.fail('request should have raised ConochError')

        def mockTryAuth(kind, user, data):
            return None

        def mockEbBadAuth(reason):
            d.errback(reason.value)

        self.patch(self.authServer, 'tryAuth', mockTryAuth)
        self.patch(self.authServer, '_cbFinishedAuth', mockCbFinishedAuth)
        self.patch(self.authServer, '_ebBadAuth', mockEbBadAuth)

        packet = NS(b'user') + NS(b'none') + NS(b'public-key') + NS(b'data')
        # If an error other than ConchError is raised, this will trigger an
        # exception.
        self.authServer.ssh_USERAUTH_REQUEST(packet)
        return self.assertFailure(d, ConchError)


    def test_verifyValidPrivateKey(self):
        """
        Test that verifying a valid private key works.
        """
        blob = keys.Key.fromString(keydata.publicRSA_openssh).blob()
        packet = (NS(b'foo') + NS(b'none') + NS(b'publickey') + b'\x00'
                + NS(b'ssh-rsa') + NS(blob))
        d = self.authServer.ssh_USERAUTH_REQUEST(packet)
        def check(ignored):
            self.assertEqual(self.authServer.transport.packets,
                    [(userauth.MSG_USERAUTH_PK_OK, NS(b'ssh-rsa') + NS(blob))])
        return d.addCallback(check)


    def test_failedPrivateKeyAuthenticationWithoutSignature(self):
        """
        Test that private key authentication fails when the public key
        is invalid.
        """
        blob = keys.Key.fromString(keydata.publicDSA_openssh).blob()
        packet = (NS(b'foo') + NS(b'none') + NS(b'publickey') + b'\x00'
                + NS(b'ssh-dsa') + NS(blob))
        d = self.authServer.ssh_USERAUTH_REQUEST(packet)
        return d.addCallback(self._checkFailed)


    def test_failedPrivateKeyAuthenticationWithSignature(self):
        """
        Test that private key authentication fails when the public key
        is invalid.
        """
        blob = keys.Key.fromString(keydata.publicRSA_openssh).blob()
        obj = keys.Key.fromString(keydata.privateRSA_openssh)
        packet = (NS(b'foo') + NS(b'none') + NS(b'publickey') + b'\xff'
                + NS(b'ssh-rsa') + NS(blob) + NS(obj.sign(blob)))
        self.authServer.transport.sessionID = b'test'
        d = self.authServer.ssh_USERAUTH_REQUEST(packet)
        return d.addCallback(self._checkFailed)


    def test_ignoreUnknownCredInterfaces(self):
        """
        L{SSHUserAuthServer} sets up
        C{SSHUserAuthServer.supportedAuthentications} by checking the portal's
        credentials interfaces and mapping them to SSH authentication method
        strings.  If the Portal advertises an interface that
        L{SSHUserAuthServer} can't map, it should be ignored.  This is a white
        box test.
        """
        server = userauth.SSHUserAuthServer()
        server.transport = FakeTransport(self.portal)
        self.portal.registerChecker(AnonymousChecker())
        server.serviceStarted()
        server.serviceStopped()
        server.supportedAuthentications.sort() # give a consistent order
        self.assertEqual(server.supportedAuthentications,
                          [b'password', b'publickey'])


    def test_removePasswordIfUnencrypted(self):
        """
        Test that the userauth service does not advertise password
        authentication if the password would be send in cleartext.
        """
        self.assertIn(b'password', self.authServer.supportedAuthentications)
        # no encryption
        clearAuthServer = userauth.SSHUserAuthServer()
        clearAuthServer.transport = FakeTransport(self.portal)
        clearAuthServer.transport.isEncrypted = lambda x: False
        clearAuthServer.serviceStarted()
        clearAuthServer.serviceStopped()
        self.assertNotIn(b'password', clearAuthServer.supportedAuthentications)
        # only encrypt incoming (the direction the password is sent)
        halfAuthServer = userauth.SSHUserAuthServer()
        halfAuthServer.transport = FakeTransport(self.portal)
        halfAuthServer.transport.isEncrypted = lambda x: x == 'in'
        halfAuthServer.serviceStarted()
        halfAuthServer.serviceStopped()
        self.assertIn(b'password', halfAuthServer.supportedAuthentications)


    def test_unencryptedConnectionWithoutPasswords(self):
        """
        If the L{SSHUserAuthServer} is not advertising passwords, then an
        unencrypted connection should not cause any warnings or exceptions.
        This is a white box test.
        """
        # create a Portal without password authentication
        portal = Portal(self.realm)
        portal.registerChecker(PrivateKeyChecker())

        # no encryption
        clearAuthServer = userauth.SSHUserAuthServer()
        clearAuthServer.transport = FakeTransport(portal)
        clearAuthServer.transport.isEncrypted = lambda x: False
        clearAuthServer.serviceStarted()
        clearAuthServer.serviceStopped()
        self.assertEqual(clearAuthServer.supportedAuthentications,
                          [b'publickey'])

        # only encrypt incoming (the direction the password is sent)
        halfAuthServer = userauth.SSHUserAuthServer()
        halfAuthServer.transport = FakeTransport(portal)
        halfAuthServer.transport.isEncrypted = lambda x: x == 'in'
        halfAuthServer.serviceStarted()
        halfAuthServer.serviceStopped()
        self.assertEqual(clearAuthServer.supportedAuthentications,
                          [b'publickey'])


    def test_loginTimeout(self):
        """
        Test that the login times out.
        """
        timeoutAuthServer = userauth.SSHUserAuthServer()
        timeoutAuthServer.clock = task.Clock()
        timeoutAuthServer.transport = FakeTransport(self.portal)
        timeoutAuthServer.serviceStarted()
        timeoutAuthServer.clock.advance(11 * 60 * 60)
        timeoutAuthServer.serviceStopped()
        self.assertEqual(timeoutAuthServer.transport.packets,
                [(transport.MSG_DISCONNECT,
                b'\x00' * 3 +
                chr(transport.DISCONNECT_NO_MORE_AUTH_METHODS_AVAILABLE) +
                NS(b"you took too long") + NS(b''))])
        self.assertTrue(timeoutAuthServer.transport.lostConnection)


    def test_cancelLoginTimeout(self):
        """
        Test that stopping the service also stops the login timeout.
        """
        timeoutAuthServer = userauth.SSHUserAuthServer()
        timeoutAuthServer.clock = task.Clock()
        timeoutAuthServer.transport = FakeTransport(self.portal)
        timeoutAuthServer.serviceStarted()
        timeoutAuthServer.serviceStopped()
        timeoutAuthServer.clock.advance(11 * 60 * 60)
        self.assertEqual(timeoutAuthServer.transport.packets, [])
        self.assertFalse(timeoutAuthServer.transport.lostConnection)


    def test_tooManyAttempts(self):
        """
        Test that the server disconnects if the client fails authentication
        too many times.
        """
        packet = b''.join([NS(b'foo'), NS(b'none'), NS(b'password'), chr(0),
                           NS(b'bar')])
        self.authServer.clock = task.Clock()
        for i in range(21):
            d = self.authServer.ssh_USERAUTH_REQUEST(packet)
            self.authServer.clock.advance(2)
        def check(ignored):
            self.assertEqual(self.authServer.transport.packets[-1],
                (transport.MSG_DISCONNECT,
                b'\x00' * 3 +
                chr(transport.DISCONNECT_NO_MORE_AUTH_METHODS_AVAILABLE) +
                NS(b"too many bad auths") + NS(b'')))
        return d.addCallback(check)


    def test_failIfUnknownService(self):
        """
        If the user requests a service that we don't support, the
        authentication should fail.
        """
        packet = NS(b'foo') + NS(b'') + NS(b'password') + chr(0) + NS(b'foo')
        self.authServer.clock = task.Clock()
        d = self.authServer.ssh_USERAUTH_REQUEST(packet)
        return d.addCallback(self._checkFailed)


    def test_tryAuthEdgeCases(self):
        """
        tryAuth() has two edge cases that are difficult to reach.

        1) an authentication method auth_* returns None instead of a Deferred.
        2) an authentication type that is defined does not have a matching
           auth_* method.

        Both these cases should return a Deferred which fails with a
        ConchError.
        """
        def mockAuth(packet):
            return None

        self.patch(self.authServer, 'auth_publickey', mockAuth) # first case
        self.patch(self.authServer, 'auth_password', None) # second case

        def secondTest(ignored):
            d2 = self.authServer.tryAuth(b'password', None, None)
            return self.assertFailure(d2, ConchError)

        d1 = self.authServer.tryAuth(b'publickey', None, None)
        return self.assertFailure(d1, ConchError).addCallback(secondTest)



class SSHUserAuthClientTests(unittest.TestCase):
    """
    Tests for SSHUserAuthClient.
    """

    if keys is None:
        skip = "cannot run without cryptography"


    def setUp(self):
        self.authClient = ClientUserAuth(b'foo', FakeTransport.Service())
        self.authClient.transport = FakeTransport(None)
        self.authClient.transport.sessionID = b'test'
        self.authClient.serviceStarted()


    def tearDown(self):
        self.authClient.serviceStopped()
        self.authClient = None


    def test_init(self):
        """
        Test that client is initialized properly.
        """
        self.assertEqual(self.authClient.user, b'foo')
        self.assertEqual(self.authClient.instance.name, b'nancy')
        self.assertEqual(self.authClient.transport.packets,
                [(userauth.MSG_USERAUTH_REQUEST, NS(b'foo') + NS(b'nancy')
                    + NS(b'none'))])


    def test_USERAUTH_SUCCESS(self):
        """
        Test that the client succeeds properly.
        """
        instance = [None]
        def stubSetService(service):
            instance[0] = service
        self.authClient.transport.setService = stubSetService
        self.authClient.ssh_USERAUTH_SUCCESS(b'')
        self.assertEqual(instance[0], self.authClient.instance)


    def test_publickey(self):
        """
        Test that the client can authenticate with a public key.
        """
        self.authClient.ssh_USERAUTH_FAILURE(NS(b'publickey') + b'\x00')
        self.assertEqual(self.authClient.transport.packets[-1],
                (userauth.MSG_USERAUTH_REQUEST, NS(b'foo') + NS(b'nancy')
                    + NS(b'publickey') + b'\x00' + NS(b'ssh-dss')
                    + NS(keys.Key.fromString(
                        keydata.publicDSA_openssh).blob())))
       # that key isn't good
        self.authClient.ssh_USERAUTH_FAILURE(NS(b'publickey') + b'\x00')
        blob = NS(keys.Key.fromString(keydata.publicRSA_openssh).blob())
        self.assertEqual(self.authClient.transport.packets[-1],
                (userauth.MSG_USERAUTH_REQUEST, (NS(b'foo') + NS(b'nancy')
                    + NS(b'publickey') + b'\x00' + NS(b'ssh-rsa') + blob)))
        self.authClient.ssh_USERAUTH_PK_OK(NS(b'ssh-rsa')
            + NS(keys.Key.fromString(keydata.publicRSA_openssh).blob()))
        sigData = (NS(self.authClient.transport.sessionID)
                + chr(userauth.MSG_USERAUTH_REQUEST) + NS(b'foo')
                + NS(b'nancy') + NS(b'publickey') + b'\x01' + NS(b'ssh-rsa')
                + blob)
        obj = keys.Key.fromString(keydata.privateRSA_openssh)
        self.assertEqual(self.authClient.transport.packets[-1],
                (userauth.MSG_USERAUTH_REQUEST, NS(b'foo') + NS(b'nancy')
                    + NS(b'publickey') + b'\x01' + NS(b'ssh-rsa') + blob
                    + NS(obj.sign(sigData))))


    def test_publickey_without_privatekey(self):
        """
        If the SSHUserAuthClient doesn't return anything from signData,
        the client should start the authentication over again by requesting
        'none' authentication.
        """
        authClient = ClientAuthWithoutPrivateKey(b'foo',
                                                 FakeTransport.Service())

        authClient.transport = FakeTransport(None)
        authClient.transport.sessionID = b'test'
        authClient.serviceStarted()
        authClient.tryAuth(b'publickey')
        authClient.transport.packets = []
        self.assertIsNone(authClient.ssh_USERAUTH_PK_OK(b''))
        self.assertEqual(authClient.transport.packets, [
                (userauth.MSG_USERAUTH_REQUEST, NS(b'foo') + NS(b'nancy') +
                 NS(b'none'))])


    def test_no_publickey(self):
        """
        If there's no public key, auth_publickey should return a Deferred
        called back with a False value.
        """
        self.authClient.getPublicKey = lambda x: None
        d = self.authClient.tryAuth(b'publickey')
        def check(result):
            self.assertFalse(result)
        return d.addCallback(check)


    def test_password(self):
        """
        Test that the client can authentication with a password.  This
        includes changing the password.
        """
        self.authClient.ssh_USERAUTH_FAILURE(NS(b'password') + b'\x00')
        self.assertEqual(self.authClient.transport.packets[-1],
                (userauth.MSG_USERAUTH_REQUEST, NS(b'foo') + NS(b'nancy')
                    + NS(b'password') + b'\x00' + NS(b'foo')))
        self.authClient.ssh_USERAUTH_PK_OK(NS(b'') + NS(b''))
        self.assertEqual(self.authClient.transport.packets[-1],
                (userauth.MSG_USERAUTH_REQUEST, NS(b'foo') + NS(b'nancy')
                    + NS(b'password') + b'\xff' + NS(b'foo') * 2))


    def test_no_password(self):
        """
        If getPassword returns None, tryAuth should return False.
        """
        self.authClient.getPassword = lambda: None
        self.assertFalse(self.authClient.tryAuth(b'password'))


    def test_USERAUTH_PK_OK_unknown_method(self):
        """
        If C{SSHUserAuthClient} gets a MSG_USERAUTH_PK_OK packet when it's not
        expecting it, it should fail the current authentication and move on to
        the next type.
        """
        self.authClient.lastAuth = b'unknown'
        self.authClient.transport.packets = []
        self.authClient.ssh_USERAUTH_PK_OK(b'')
        self.assertEqual(self.authClient.transport.packets,
                          [(userauth.MSG_USERAUTH_REQUEST, NS(b'foo') +
                            NS(b'nancy') + NS(b'none'))])


    def test_USERAUTH_FAILURE_sorting(self):
        """
        ssh_USERAUTH_FAILURE should sort the methods by their position
        in SSHUserAuthClient.preferredOrder.  Methods that are not in
        preferredOrder should be sorted at the end of that list.
        """
        def auth_firstmethod():
            self.authClient.transport.sendPacket(255, b'here is data')
        def auth_anothermethod():
            self.authClient.transport.sendPacket(254, b'other data')
            return True
        self.authClient.auth_firstmethod = auth_firstmethod
        self.authClient.auth_anothermethod = auth_anothermethod

        # although they shouldn't get called, method callbacks auth_* MUST
        # exist in order for the test to work properly.
        self.authClient.ssh_USERAUTH_FAILURE(NS(b'anothermethod,password') +
                                             b'\x00')
        # should send password packet
        self.assertEqual(self.authClient.transport.packets[-1],
                (userauth.MSG_USERAUTH_REQUEST, NS(b'foo') + NS(b'nancy')
                    + NS(b'password') + b'\x00' + NS(b'foo')))
        self.authClient.ssh_USERAUTH_FAILURE(
            NS(b'firstmethod,anothermethod,password') + b'\xff')
        self.assertEqual(self.authClient.transport.packets[-2:],
                          [(255, b'here is data'), (254, b'other data')])


    def test_disconnectIfNoMoreAuthentication(self):
        """
        If there are no more available user authentication messages,
        the SSHUserAuthClient should disconnect with code
        DISCONNECT_NO_MORE_AUTH_METHODS_AVAILABLE.
        """
        self.authClient.ssh_USERAUTH_FAILURE(NS(b'password') + b'\x00')
        self.authClient.ssh_USERAUTH_FAILURE(NS(b'password') + b'\xff')
        self.assertEqual(self.authClient.transport.packets[-1],
                          (transport.MSG_DISCONNECT, b'\x00\x00\x00\x0e' +
                           NS(b'no more authentication methods available') +
                           b'\x00\x00\x00\x00'))


    def test_ebAuth(self):
        """
        _ebAuth (the generic authentication error handler) should send
        a request for the 'none' authentication method.
        """
        self.authClient.transport.packets = []
        self.authClient._ebAuth(None)
        self.assertEqual(self.authClient.transport.packets,
                [(userauth.MSG_USERAUTH_REQUEST, NS(b'foo') + NS(b'nancy')
                    + NS(b'none'))])


    def test_defaults(self):
        """
        getPublicKey() should return None.  getPrivateKey() should return a
        failed Deferred.  getPassword() should return a failed Deferred.
        getGenericAnswers() should return a failed Deferred.
        """
        authClient = userauth.SSHUserAuthClient(b'foo',
                                                FakeTransport.Service())
        self.assertIsNone(authClient.getPublicKey())
        def check(result):
            result.trap(NotImplementedError)
            d = authClient.getPassword()
            return d.addCallback(self.fail).addErrback(check2)
        def check2(result):
            result.trap(NotImplementedError)
            d = authClient.getGenericAnswers(None, None, None)
            return d.addCallback(self.fail).addErrback(check3)
        def check3(result):
            result.trap(NotImplementedError)
        d = authClient.getPrivateKey()
        return d.addCallback(self.fail).addErrback(check)



class LoopbackTests(unittest.TestCase):

    if keys is None:
        skip = "cannot run without cryptography or PyASN1"


    class Factory:
        class Service:
            name = b'TestService'


            def serviceStarted(self):
                self.transport.loseConnection()


            def serviceStopped(self):
                pass


        def getService(self, avatar, name):
            return self.Service


    def test_loopback(self):
        """
        Test that the userauth server and client play nicely with each other.
        """
        server = userauth.SSHUserAuthServer()
        client = ClientUserAuth(b'foo', self.Factory.Service())

        # set up transports
        server.transport = transport.SSHTransportBase()
        server.transport.service = server
        server.transport.isEncrypted = lambda x: True
        client.transport = transport.SSHTransportBase()
        client.transport.service = client
        server.transport.sessionID = client.transport.sessionID = b''
        # don't send key exchange packet
        server.transport.sendKexInit = client.transport.sendKexInit = \
                lambda: None

        # set up server authentication
        server.transport.factory = self.Factory()
        server.passwordDelay = 0 # remove bad password delay
        realm = Realm()
        portal = Portal(realm)
        checker = SSHProtocolChecker()
        checker.registerChecker(PasswordChecker())
        checker.registerChecker(PrivateKeyChecker())
        checker.areDone = lambda aId: (
            len(checker.successfulCredentials[aId]) == 2)
        portal.registerChecker(checker)
        server.transport.factory.portal = portal

        d = loopback.loopbackAsync(server.transport, client.transport)
        server.transport.transport.logPrefix = lambda: '_ServerLoopback'
        client.transport.transport.logPrefix = lambda: '_ClientLoopback'

        server.serviceStarted()
        client.serviceStarted()

        def check(ignored):
            self.assertEqual(server.transport.service.name, b'TestService')
        return d.addCallback(check)



class ModuleInitializationTests(unittest.TestCase):
    if keys is None:
        skip = "cannot run without cryptography or PyASN1"


    def test_messages(self):
        # Several message types have value 60, check that MSG_USERAUTH_PK_OK
        # is always the one which is mapped.
        self.assertEqual(userauth.SSHUserAuthServer.protocolMessages[60],
                         'MSG_USERAUTH_PK_OK')
        self.assertEqual(userauth.SSHUserAuthClient.protocolMessages[60],
                         'MSG_USERAUTH_PK_OK')

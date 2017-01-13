# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.conch.ssh.agent}.
"""
from __future__ import absolute_import, division

import struct

from twisted.trial import unittest
from twisted.test import iosim

try:
    import cryptography
except ImportError:
    cryptography = None

try:
    import pyasn1
except ImportError:
    pyasn1 = None

if cryptography and pyasn1:
    from twisted.conch.ssh import keys, agent
else:
    keys = agent = None

from twisted.conch.test import keydata
from twisted.conch.error import ConchError, MissingKeyStoreError


class StubFactory(object):
    """
    Mock factory that provides the keys attribute required by the
    SSHAgentServerProtocol
    """
    def __init__(self):
        self.keys = {}



class AgentTestBase(unittest.TestCase):
    """
    Tests for SSHAgentServer/Client.
    """
    if iosim is None:
        skip = "iosim requires SSL, but SSL is not available"
    elif agent is None or keys is None:
        skip = "Cannot run without cryptography or PyASN1"

    def setUp(self):
        # wire up our client <-> server
        self.client, self.server, self.pump = iosim.connectedServerAndClient(
            agent.SSHAgentServer, agent.SSHAgentClient)

        # the server's end of the protocol is stateful and we store it on the
        # factory, for which we only need a mock
        self.server.factory = StubFactory()

        # pub/priv keys of each kind
        self.rsaPrivate = keys.Key.fromString(keydata.privateRSA_openssh)
        self.dsaPrivate = keys.Key.fromString(keydata.privateDSA_openssh)

        self.rsaPublic = keys.Key.fromString(keydata.publicRSA_openssh)
        self.dsaPublic = keys.Key.fromString(keydata.publicDSA_openssh)



class ServerProtocolContractWithFactoryTests(AgentTestBase):
    """
    The server protocol is stateful and so uses its factory to track state
    across requests.  This test asserts that the protocol raises if its factory
    doesn't provide the necessary storage for that state.
    """
    def test_factorySuppliesKeyStorageForServerProtocol(self):
        # need a message to send into the server
        msg = struct.pack('!LB',1, agent.AGENTC_REQUEST_IDENTITIES)
        del self.server.factory.__dict__['keys']
        self.assertRaises(MissingKeyStoreError,
                          self.server.dataReceived, msg)



class UnimplementedVersionOneServerTests(AgentTestBase):
    """
    Tests for methods with no-op implementations on the server. We need these
    for clients, such as openssh, that try v1 methods before going to v2.

    Because the client doesn't expose these operations with nice method names,
    we invoke sendRequest directly with an op code.
    """

    def test_agentc_REQUEST_RSA_IDENTITIES(self):
        """
        assert that we get the correct op code for an RSA identities request
        """
        d = self.client.sendRequest(agent.AGENTC_REQUEST_RSA_IDENTITIES, b'')
        self.pump.flush()
        def _cb(packet):
            self.assertEqual(
                agent.AGENT_RSA_IDENTITIES_ANSWER, ord(packet[0:1]))
        return d.addCallback(_cb)


    def test_agentc_REMOVE_RSA_IDENTITY(self):
        """
        assert that we get the correct op code for an RSA remove identity request
        """
        d = self.client.sendRequest(agent.AGENTC_REMOVE_RSA_IDENTITY, b'')
        self.pump.flush()
        return d.addCallback(self.assertEqual, b'')


    def test_agentc_REMOVE_ALL_RSA_IDENTITIES(self):
        """
        assert that we get the correct op code for an RSA remove all identities
        request.
        """
        d = self.client.sendRequest(agent.AGENTC_REMOVE_ALL_RSA_IDENTITIES, b'')
        self.pump.flush()
        return d.addCallback(self.assertEqual, b'')



if agent is not None:
    class CorruptServer(agent.SSHAgentServer):
        """
        A misbehaving server that returns bogus response op codes so that we can
        verify that our callbacks that deal with these op codes handle such
        miscreants.
        """
        def agentc_REQUEST_IDENTITIES(self, data):
            self.sendResponse(254, b'')


        def agentc_SIGN_REQUEST(self, data):
            self.sendResponse(254, b'')



class ClientWithBrokenServerTests(AgentTestBase):
    """
    verify error handling code in the client using a misbehaving server
    """

    def setUp(self):
        AgentTestBase.setUp(self)
        self.client, self.server, self.pump = iosim.connectedServerAndClient(
            CorruptServer, agent.SSHAgentClient)
        # the server's end of the protocol is stateful and we store it on the
        # factory, for which we only need a mock
        self.server.factory = StubFactory()


    def test_signDataCallbackErrorHandling(self):
        """
        Assert that L{SSHAgentClient.signData} raises a ConchError
        if we get a response from the server whose opcode doesn't match
        the protocol for data signing requests.
        """
        d = self.client.signData(self.rsaPublic.blob(), b"John Hancock")
        self.pump.flush()
        return self.assertFailure(d, ConchError)


    def test_requestIdentitiesCallbackErrorHandling(self):
        """
        Assert that L{SSHAgentClient.requestIdentities} raises a ConchError
        if we get a response from the server whose opcode doesn't match
        the protocol for identity requests.
        """
        d = self.client.requestIdentities()
        self.pump.flush()
        return self.assertFailure(d, ConchError)



class AgentKeyAdditionTests(AgentTestBase):
    """
    Test adding different flavors of keys to an agent.
    """

    def test_addRSAIdentityNoComment(self):
        """
        L{SSHAgentClient.addIdentity} adds the private key it is called
        with to the SSH agent server to which it is connected, associating
        it with the comment it is called with.

        This test asserts that omitting the comment produces an
        empty string for the comment on the server.
        """
        d = self.client.addIdentity(self.rsaPrivate.privateBlob())
        self.pump.flush()
        def _check(ignored):
            serverKey = self.server.factory.keys[self.rsaPrivate.blob()]
            self.assertEqual(self.rsaPrivate, serverKey[0])
            self.assertEqual(b'', serverKey[1])
        return d.addCallback(_check)


    def test_addDSAIdentityNoComment(self):
        """
        L{SSHAgentClient.addIdentity} adds the private key it is called
        with to the SSH agent server to which it is connected, associating
        it with the comment it is called with.

        This test asserts that omitting the comment produces an
        empty string for the comment on the server.
        """
        d = self.client.addIdentity(self.dsaPrivate.privateBlob())
        self.pump.flush()
        def _check(ignored):
            serverKey = self.server.factory.keys[self.dsaPrivate.blob()]
            self.assertEqual(self.dsaPrivate, serverKey[0])
            self.assertEqual(b'', serverKey[1])
        return d.addCallback(_check)


    def test_addRSAIdentityWithComment(self):
        """
        L{SSHAgentClient.addIdentity} adds the private key it is called
        with to the SSH agent server to which it is connected, associating
        it with the comment it is called with.

        This test asserts that the server receives/stores the comment
        as sent by the client.
        """
        d = self.client.addIdentity(
            self.rsaPrivate.privateBlob(), comment=b'My special key')
        self.pump.flush()
        def _check(ignored):
            serverKey = self.server.factory.keys[self.rsaPrivate.blob()]
            self.assertEqual(self.rsaPrivate, serverKey[0])
            self.assertEqual(b'My special key', serverKey[1])
        return d.addCallback(_check)


    def test_addDSAIdentityWithComment(self):
        """
        L{SSHAgentClient.addIdentity} adds the private key it is called
        with to the SSH agent server to which it is connected, associating
        it with the comment it is called with.

        This test asserts that the server receives/stores the comment
        as sent by the client.
        """
        d = self.client.addIdentity(
            self.dsaPrivate.privateBlob(), comment=b'My special key')
        self.pump.flush()
        def _check(ignored):
            serverKey = self.server.factory.keys[self.dsaPrivate.blob()]
            self.assertEqual(self.dsaPrivate, serverKey[0])
            self.assertEqual(b'My special key', serverKey[1])
        return d.addCallback(_check)



class AgentClientFailureTests(AgentTestBase):
    def test_agentFailure(self):
        """
        verify that the client raises ConchError on AGENT_FAILURE
        """
        d = self.client.sendRequest(254, b'')
        self.pump.flush()
        return self.assertFailure(d, ConchError)



class AgentIdentityRequestsTests(AgentTestBase):
    """
    Test operations against a server with identities already loaded.
    """

    def setUp(self):
        AgentTestBase.setUp(self)
        self.server.factory.keys[self.dsaPrivate.blob()] = (
            self.dsaPrivate, b'a comment')
        self.server.factory.keys[self.rsaPrivate.blob()] = (
            self.rsaPrivate, b'another comment')


    def test_signDataRSA(self):
        """
        Sign data with an RSA private key and then verify it with the public
        key.
        """
        d = self.client.signData(self.rsaPublic.blob(), b"John Hancock")
        self.pump.flush()
        signature = self.successResultOf(d)

        expected = self.rsaPrivate.sign(b"John Hancock")
        self.assertEqual(expected, signature)
        self.assertTrue(self.rsaPublic.verify(signature, b"John Hancock"))


    def test_signDataDSA(self):
        """
        Sign data with a DSA private key and then verify it with the public
        key.
        """
        d = self.client.signData(self.dsaPublic.blob(), b"John Hancock")
        self.pump.flush()
        def _check(sig):
            # Cannot do this b/c DSA uses random numbers when signing
            #   expected = self.dsaPrivate.sign("John Hancock")
            #   self.assertEqual(expected, sig)
            self.assertTrue(self.dsaPublic.verify(sig, b"John Hancock"))
        return d.addCallback(_check)


    def test_signDataRSAErrbackOnUnknownBlob(self):
        """
        Assert that we get an errback if we try to sign data using a key that
        wasn't added.
        """
        del self.server.factory.keys[self.rsaPublic.blob()]
        d = self.client.signData(self.rsaPublic.blob(), b"John Hancock")
        self.pump.flush()
        return self.assertFailure(d, ConchError)


    def test_requestIdentities(self):
        """
        Assert that we get all of the keys/comments that we add when we issue a
        request for all identities.
        """
        d = self.client.requestIdentities()
        self.pump.flush()
        def _check(keyt):
            expected = {}
            expected[self.dsaPublic.blob()] = b'a comment'
            expected[self.rsaPublic.blob()] = b'another comment'

            received = {}
            for k in keyt:
                received[keys.Key.fromString(k[0], type='blob').blob()] = k[1]
            self.assertEqual(expected, received)
        return d.addCallback(_check)



class AgentKeyRemovalTests(AgentTestBase):
    """
    Test support for removing keys in a remote server.
    """

    def setUp(self):
        AgentTestBase.setUp(self)
        self.server.factory.keys[self.dsaPrivate.blob()] = (
            self.dsaPrivate, b'a comment')
        self.server.factory.keys[self.rsaPrivate.blob()] = (
            self.rsaPrivate, b'another comment')


    def test_removeRSAIdentity(self):
        """
        Assert that we can remove an RSA identity.
        """
        # only need public key for this
        d = self.client.removeIdentity(self.rsaPrivate.blob())
        self.pump.flush()

        def _check(ignored):
            self.assertEqual(1, len(self.server.factory.keys))
            self.assertIn(self.dsaPrivate.blob(), self.server.factory.keys)
            self.assertNotIn(self.rsaPrivate.blob(), self.server.factory.keys)
        return d.addCallback(_check)


    def test_removeDSAIdentity(self):
        """
        Assert that we can remove a DSA identity.
        """
        # only need public key for this
        d = self.client.removeIdentity(self.dsaPrivate.blob())
        self.pump.flush()

        def _check(ignored):
            self.assertEqual(1, len(self.server.factory.keys))
            self.assertIn(self.rsaPrivate.blob(), self.server.factory.keys)
        return d.addCallback(_check)


    def test_removeAllIdentities(self):
        """
        Assert that we can remove all identities.
        """
        d = self.client.removeAllIdentities()
        self.pump.flush()

        def _check(ignored):
            self.assertEqual(0, len(self.server.factory.keys))
        return d.addCallback(_check)

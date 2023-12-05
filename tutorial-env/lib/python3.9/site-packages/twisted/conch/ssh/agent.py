# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implements the SSH v2 key agent protocol.  This protocol is documented in the
SSH source code, in the file
U{PROTOCOL.agent<http://www.openbsd.org/cgi-bin/cvsweb/src/usr.bin/ssh/PROTOCOL.agent>}.

Maintainer: Paul Swartz
"""


import struct

from twisted.conch.error import ConchError, MissingKeyStoreError
from twisted.conch.ssh import keys
from twisted.conch.ssh.common import NS, getMP, getNS
from twisted.internet import defer, protocol


class SSHAgentClient(protocol.Protocol):
    """
    The client side of the SSH agent protocol.  This is equivalent to
    ssh-add(1) and can be used with either ssh-agent(1) or the SSHAgentServer
    protocol, also in this package.
    """

    def __init__(self):
        self.buf = b""
        self.deferreds = []

    def dataReceived(self, data):
        self.buf += data
        while 1:
            if len(self.buf) <= 4:
                return
            packLen = struct.unpack("!L", self.buf[:4])[0]
            if len(self.buf) < 4 + packLen:
                return
            packet, self.buf = self.buf[4 : 4 + packLen], self.buf[4 + packLen :]
            reqType = ord(packet[0:1])
            d = self.deferreds.pop(0)
            if reqType == AGENT_FAILURE:
                d.errback(ConchError("agent failure"))
            elif reqType == AGENT_SUCCESS:
                d.callback(b"")
            else:
                d.callback(packet)

    def sendRequest(self, reqType, data):
        pack = struct.pack("!LB", len(data) + 1, reqType) + data
        self.transport.write(pack)
        d = defer.Deferred()
        self.deferreds.append(d)
        return d

    def requestIdentities(self):
        """
        @return: A L{Deferred} which will fire with a list of all keys found in
            the SSH agent. The list of keys is comprised of (public key blob,
            comment) tuples.
        """
        d = self.sendRequest(AGENTC_REQUEST_IDENTITIES, b"")
        d.addCallback(self._cbRequestIdentities)
        return d

    def _cbRequestIdentities(self, data):
        """
        Unpack a collection of identities into a list of tuples comprised of
        public key blobs and comments.
        """
        if ord(data[0:1]) != AGENT_IDENTITIES_ANSWER:
            raise ConchError("unexpected response: %i" % ord(data[0:1]))
        numKeys = struct.unpack("!L", data[1:5])[0]
        result = []
        data = data[5:]
        for i in range(numKeys):
            blob, data = getNS(data)
            comment, data = getNS(data)
            result.append((blob, comment))
        return result

    def addIdentity(self, blob, comment=b""):
        """
        Add a private key blob to the agent's collection of keys.
        """
        req = blob
        req += NS(comment)
        return self.sendRequest(AGENTC_ADD_IDENTITY, req)

    def signData(self, blob, data):
        """
        Request that the agent sign the given C{data} with the private key
        which corresponds to the public key given by C{blob}.  The private
        key should have been added to the agent already.

        @type blob: L{bytes}
        @type data: L{bytes}
        @return: A L{Deferred} which fires with a signature for given data
            created with the given key.
        """
        req = NS(blob)
        req += NS(data)
        req += b"\000\000\000\000"  # flags
        return self.sendRequest(AGENTC_SIGN_REQUEST, req).addCallback(self._cbSignData)

    def _cbSignData(self, data):
        if ord(data[0:1]) != AGENT_SIGN_RESPONSE:
            raise ConchError("unexpected data: %i" % ord(data[0:1]))
        signature = getNS(data[1:])[0]
        return signature

    def removeIdentity(self, blob):
        """
        Remove the private key corresponding to the public key in blob from the
        running agent.
        """
        req = NS(blob)
        return self.sendRequest(AGENTC_REMOVE_IDENTITY, req)

    def removeAllIdentities(self):
        """
        Remove all keys from the running agent.
        """
        return self.sendRequest(AGENTC_REMOVE_ALL_IDENTITIES, b"")


class SSHAgentServer(protocol.Protocol):
    """
    The server side of the SSH agent protocol.  This is equivalent to
    ssh-agent(1) and can be used with either ssh-add(1) or the SSHAgentClient
    protocol, also in this package.
    """

    def __init__(self):
        self.buf = b""

    def dataReceived(self, data):
        self.buf += data
        while 1:
            if len(self.buf) <= 4:
                return
            packLen = struct.unpack("!L", self.buf[:4])[0]
            if len(self.buf) < 4 + packLen:
                return
            packet, self.buf = self.buf[4 : 4 + packLen], self.buf[4 + packLen :]
            reqType = ord(packet[0:1])
            reqName = messages.get(reqType, None)
            if not reqName:
                self.sendResponse(AGENT_FAILURE, b"")
            else:
                f = getattr(self, "agentc_%s" % reqName)
                if getattr(self.factory, "keys", None) is None:
                    self.sendResponse(AGENT_FAILURE, b"")
                    raise MissingKeyStoreError()
                f(packet[1:])

    def sendResponse(self, reqType, data):
        pack = struct.pack("!LB", len(data) + 1, reqType) + data
        self.transport.write(pack)

    def agentc_REQUEST_IDENTITIES(self, data):
        """
        Return all of the identities that have been added to the server
        """
        assert data == b""
        numKeys = len(self.factory.keys)
        resp = []

        resp.append(struct.pack("!L", numKeys))
        for key, comment in self.factory.keys.values():
            resp.append(NS(key.blob()))  # yes, wrapped in an NS
            resp.append(NS(comment))
        self.sendResponse(AGENT_IDENTITIES_ANSWER, b"".join(resp))

    def agentc_SIGN_REQUEST(self, data):
        """
        Data is a structure with a reference to an already added key object and
        some data that the clients wants signed with that key.  If the key
        object wasn't loaded, return AGENT_FAILURE, else return the signature.
        """
        blob, data = getNS(data)
        if blob not in self.factory.keys:
            return self.sendResponse(AGENT_FAILURE, b"")
        signData, data = getNS(data)
        assert data == b"\000\000\000\000"
        self.sendResponse(
            AGENT_SIGN_RESPONSE, NS(self.factory.keys[blob][0].sign(signData))
        )

    def agentc_ADD_IDENTITY(self, data):
        """
        Adds a private key to the agent's collection of identities.  On
        subsequent interactions, the private key can be accessed using only the
        corresponding public key.
        """

        # need to pre-read the key data so we can get past it to the comment string
        keyType, rest = getNS(data)
        if keyType == b"ssh-rsa":
            nmp = 6
        elif keyType == b"ssh-dss":
            nmp = 5
        else:
            raise keys.BadKeyError("unknown blob type: %s" % keyType)

        rest = getMP(rest, nmp)[
            -1
        ]  # ignore the key data for now, we just want the comment
        comment, rest = getNS(rest)  # the comment, tacked onto the end of the key blob

        k = keys.Key.fromString(data, type="private_blob")  # not wrapped in NS here
        self.factory.keys[k.blob()] = (k, comment)
        self.sendResponse(AGENT_SUCCESS, b"")

    def agentc_REMOVE_IDENTITY(self, data):
        """
        Remove a specific key from the agent's collection of identities.
        """
        blob, _ = getNS(data)
        k = keys.Key.fromString(blob, type="blob")
        del self.factory.keys[k.blob()]
        self.sendResponse(AGENT_SUCCESS, b"")

    def agentc_REMOVE_ALL_IDENTITIES(self, data):
        """
        Remove all keys from the agent's collection of identities.
        """
        assert data == b""
        self.factory.keys = {}
        self.sendResponse(AGENT_SUCCESS, b"")

    # v1 messages that we ignore because we don't keep v1 keys
    # open-ssh sends both v1 and v2 commands, so we have to
    # do no-ops for v1 commands or we'll get "bad request" errors

    def agentc_REQUEST_RSA_IDENTITIES(self, data):
        """
        v1 message for listing RSA1 keys; superseded by
        agentc_REQUEST_IDENTITIES, which handles different key types.
        """
        self.sendResponse(AGENT_RSA_IDENTITIES_ANSWER, struct.pack("!L", 0))

    def agentc_REMOVE_RSA_IDENTITY(self, data):
        """
        v1 message for removing RSA1 keys; superseded by
        agentc_REMOVE_IDENTITY, which handles different key types.
        """
        self.sendResponse(AGENT_SUCCESS, b"")

    def agentc_REMOVE_ALL_RSA_IDENTITIES(self, data):
        """
        v1 message for removing all RSA1 keys; superseded by
        agentc_REMOVE_ALL_IDENTITIES, which handles different key types.
        """
        self.sendResponse(AGENT_SUCCESS, b"")


AGENTC_REQUEST_RSA_IDENTITIES = 1
AGENT_RSA_IDENTITIES_ANSWER = 2
AGENT_FAILURE = 5
AGENT_SUCCESS = 6

AGENTC_REMOVE_RSA_IDENTITY = 8
AGENTC_REMOVE_ALL_RSA_IDENTITIES = 9

AGENTC_REQUEST_IDENTITIES = 11
AGENT_IDENTITIES_ANSWER = 12
AGENTC_SIGN_REQUEST = 13
AGENT_SIGN_RESPONSE = 14
AGENTC_ADD_IDENTITY = 17
AGENTC_REMOVE_IDENTITY = 18
AGENTC_REMOVE_ALL_IDENTITIES = 19

messages = {}
for name, value in locals().copy().items():
    if name[:7] == "AGENTC_":
        messages[value] = name[7:]  # doesn't handle doubles

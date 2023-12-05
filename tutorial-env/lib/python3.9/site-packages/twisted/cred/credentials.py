# -*- test-case-name: twisted.cred.test.test_cred-*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module defines L{ICredentials}, an interface for objects that represent
authentication credentials to provide, and also includes a number of useful
implementations of that interface.
"""


import base64
import hmac
import random
import re
import time
from binascii import hexlify
from hashlib import md5

from zope.interface import Interface, implementer

from twisted.cred import error
from twisted.cred._digest import calcHA1, calcHA2, calcResponse
from twisted.python.compat import nativeString, networkString
from twisted.python.deprecate import deprecatedModuleAttribute
from twisted.python.randbytes import secureRandom
from twisted.python.versions import Version


class ICredentials(Interface):
    """
    I check credentials.

    Implementors I{must} specify the sub-interfaces of ICredentials
    to which it conforms, using L{zope.interface.implementer}.
    """


class IUsernameDigestHash(ICredentials):
    """
    This credential is used when a CredentialChecker has access to the hash
    of the username:realm:password as in an Apache .htdigest file.
    """

    def checkHash(digestHash):
        """
        @param digestHash: The hashed username:realm:password to check against.

        @return: C{True} if the credentials represented by this object match
            the given hash, C{False} if they do not, or a L{Deferred} which
            will be called back with one of these values.
        """


class IUsernameHashedPassword(ICredentials):
    """
    I encapsulate a username and a hashed password.

    This credential is used when a hashed password is received from the
    party requesting authentication.  CredentialCheckers which check this
    kind of credential must store the passwords in plaintext (or as
    password-equivalent hashes) form so that they can be hashed in a manner
    appropriate for the particular credentials class.

    @type username: L{bytes}
    @ivar username: The username associated with these credentials.
    """

    def checkPassword(password):
        """
        Validate these credentials against the correct password.

        @type password: L{bytes}
        @param password: The correct, plaintext password against which to
        check.

        @rtype: C{bool} or L{Deferred}
        @return: C{True} if the credentials represented by this object match the
            given password, C{False} if they do not, or a L{Deferred} which will
            be called back with one of these values.
        """


class IUsernamePassword(ICredentials):
    """
    I encapsulate a username and a plaintext password.

    This encapsulates the case where the password received over the network
    has been hashed with the identity function (That is, not at all).  The
    CredentialsChecker may store the password in whatever format it desires,
    it need only transform the stored password in a similar way before
    performing the comparison.

    @type username: L{bytes}
    @ivar username: The username associated with these credentials.

    @type password: L{bytes}
    @ivar password: The password associated with these credentials.
    """

    def checkPassword(password):
        """
        Validate these credentials against the correct password.

        @type password: L{bytes}
        @param password: The correct, plaintext password against which to
        check.

        @rtype: C{bool} or L{Deferred}
        @return: C{True} if the credentials represented by this object match the
            given password, C{False} if they do not, or a L{Deferred} which will
            be called back with one of these values.
        """


class IAnonymous(ICredentials):
    """
    I am an explicitly anonymous request for access.

    @see: L{twisted.cred.checkers.AllowAnonymousAccess}
    """


@implementer(IUsernameHashedPassword, IUsernameDigestHash)
class DigestedCredentials:
    """
    Yet Another Simple HTTP Digest authentication scheme.
    """

    def __init__(self, username, method, realm, fields):
        self.username = username
        self.method = method
        self.realm = realm
        self.fields = fields

    def checkPassword(self, password):
        """
        Verify that the credentials represented by this object agree with the
        given plaintext C{password} by hashing C{password} in the same way the
        response hash represented by this object was generated and comparing
        the results.
        """
        response = self.fields.get("response")
        uri = self.fields.get("uri")
        nonce = self.fields.get("nonce")
        cnonce = self.fields.get("cnonce")
        nc = self.fields.get("nc")
        algo = self.fields.get("algorithm", b"md5").lower()
        qop = self.fields.get("qop", b"auth")

        expected = calcResponse(
            calcHA1(algo, self.username, self.realm, password, nonce, cnonce),
            calcHA2(algo, self.method, uri, qop, None),
            algo,
            nonce,
            nc,
            cnonce,
            qop,
        )

        return expected == response

    def checkHash(self, digestHash):
        """
        Verify that the credentials represented by this object agree with the
        credentials represented by the I{H(A1)} given in C{digestHash}.

        @param digestHash: A precomputed H(A1) value based on the username,
            realm, and password associate with this credentials object.
        """
        response = self.fields.get("response")
        uri = self.fields.get("uri")
        nonce = self.fields.get("nonce")
        cnonce = self.fields.get("cnonce")
        nc = self.fields.get("nc")
        algo = self.fields.get("algorithm", b"md5").lower()
        qop = self.fields.get("qop", b"auth")

        expected = calcResponse(
            calcHA1(algo, None, None, None, nonce, cnonce, preHA1=digestHash),
            calcHA2(algo, self.method, uri, qop, None),
            algo,
            nonce,
            nc,
            cnonce,
            qop,
        )

        return expected == response


class DigestCredentialFactory:
    """
    Support for RFC2617 HTTP Digest Authentication

    @cvar CHALLENGE_LIFETIME_SECS: The number of seconds for which an
        opaque should be valid.

    @type privateKey: L{bytes}
    @ivar privateKey: A random string used for generating the secure opaque.

    @type algorithm: L{bytes}
    @param algorithm: Case insensitive string specifying the hash algorithm to
        use.  Must be either C{'md5'} or C{'sha'}.  C{'md5-sess'} is B{not}
        supported.

    @type authenticationRealm: L{bytes}
    @param authenticationRealm: case sensitive string that specifies the realm
        portion of the challenge
    """

    _parseparts = re.compile(
        b"([^= ]+)"  # The key
        b"="  # Conventional key/value separator (literal)
        b"(?:"  # Group together a couple options
        b'"([^"]*)"'  # A quoted string of length 0 or more
        b"|"  # The other option in the group is coming
        b"([^,]+)"  # An unquoted string of length 1 or more, up to a comma
        b")"  # That non-matching group ends
        b",?"
    )  # There might be a comma at the end (none on last pair)

    CHALLENGE_LIFETIME_SECS = 15 * 60  # 15 minutes

    scheme = b"digest"

    def __init__(self, algorithm, authenticationRealm):
        self.algorithm = algorithm
        self.authenticationRealm = authenticationRealm
        self.privateKey = secureRandom(12)

    def getChallenge(self, address):
        """
        Generate the challenge for use in the WWW-Authenticate header.

        @param address: The client address to which this challenge is being
            sent.

        @return: The L{dict} that can be used to generate a WWW-Authenticate
            header.
        """
        c = self._generateNonce()
        o = self._generateOpaque(c, address)

        return {
            "nonce": c,
            "opaque": o,
            "qop": b"auth",
            "algorithm": self.algorithm,
            "realm": self.authenticationRealm,
        }

    def _generateNonce(self):
        """
        Create a random value suitable for use as the nonce parameter of a
        WWW-Authenticate challenge.

        @rtype: L{bytes}
        """
        return hexlify(secureRandom(12))

    def _getTime(self):
        """
        Parameterize the time based seed used in C{_generateOpaque}
        so we can deterministically unittest it's behavior.
        """
        return time.time()

    def _generateOpaque(self, nonce, clientip):
        """
        Generate an opaque to be returned to the client.  This is a unique
        string that can be returned to us and verified.
        """
        # Now, what we do is encode the nonce, client ip and a timestamp in the
        # opaque value with a suitable digest.
        now = b"%d" % (int(self._getTime()),)

        if not clientip:
            clientip = b""
        elif isinstance(clientip, str):
            clientip = clientip.encode("ascii")

        key = b",".join((nonce, clientip, now))
        digest = hexlify(md5(key + self.privateKey).digest())
        ekey = base64.b64encode(key)
        return b"-".join((digest, ekey.replace(b"\n", b"")))

    def _verifyOpaque(self, opaque, nonce, clientip):
        """
        Given the opaque and nonce from the request, as well as the client IP
        that made the request, verify that the opaque was generated by us.
        And that it's not too old.

        @param opaque: The opaque value from the Digest response
        @param nonce: The nonce value from the Digest response
        @param clientip: The remote IP address of the client making the request
            or L{None} if the request was submitted over a channel where this
            does not make sense.

        @return: C{True} if the opaque was successfully verified.

        @raise error.LoginFailed: if C{opaque} could not be parsed or
            contained the wrong values.
        """
        # First split the digest from the key
        opaqueParts = opaque.split(b"-")
        if len(opaqueParts) != 2:
            raise error.LoginFailed("Invalid response, invalid opaque value")

        if not clientip:
            clientip = b""
        elif isinstance(clientip, str):
            clientip = clientip.encode("ascii")

        # Verify the key
        key = base64.b64decode(opaqueParts[1])
        keyParts = key.split(b",")

        if len(keyParts) != 3:
            raise error.LoginFailed("Invalid response, invalid opaque value")

        if keyParts[0] != nonce:
            raise error.LoginFailed(
                "Invalid response, incompatible opaque/nonce values"
            )

        if keyParts[1] != clientip:
            raise error.LoginFailed(
                "Invalid response, incompatible opaque/client values"
            )

        try:
            when = int(keyParts[2])
        except ValueError:
            raise error.LoginFailed("Invalid response, invalid opaque/time values")

        if (
            int(self._getTime()) - when
            > DigestCredentialFactory.CHALLENGE_LIFETIME_SECS
        ):

            raise error.LoginFailed(
                "Invalid response, incompatible opaque/nonce too old"
            )

        # Verify the digest
        digest = hexlify(md5(key + self.privateKey).digest())
        if digest != opaqueParts[0]:
            raise error.LoginFailed("Invalid response, invalid opaque value")

        return True

    def decode(self, response, method, host):
        """
        Decode the given response and attempt to generate a
        L{DigestedCredentials} from it.

        @type response: L{bytes}
        @param response: A string of comma separated key=value pairs

        @type method: L{bytes}
        @param method: The action requested to which this response is addressed
            (GET, POST, INVITE, OPTIONS, etc).

        @type host: L{bytes}
        @param host: The address the request was sent from.

        @raise error.LoginFailed: If the response does not contain a username,
            a nonce, an opaque, or if the opaque is invalid.

        @return: L{DigestedCredentials}
        """
        response = b" ".join(response.splitlines())
        parts = self._parseparts.findall(response)
        auth = {}
        for (key, bare, quoted) in parts:
            value = (quoted or bare).strip()
            auth[nativeString(key.strip())] = value

        username = auth.get("username")
        if not username:
            raise error.LoginFailed("Invalid response, no username given.")

        if "opaque" not in auth:
            raise error.LoginFailed("Invalid response, no opaque given.")

        if "nonce" not in auth:
            raise error.LoginFailed("Invalid response, no nonce given.")

        # Now verify the nonce/opaque values for this client
        if self._verifyOpaque(auth.get("opaque"), auth.get("nonce"), host):
            return DigestedCredentials(username, method, self.authenticationRealm, auth)


@implementer(IUsernameHashedPassword)
class CramMD5Credentials:
    """
    An encapsulation of some CramMD5 hashed credentials.

    @ivar challenge: The challenge to be sent to the client.
    @type challenge: L{bytes}

    @ivar response: The hashed response from the client.
    @type response: L{bytes}

    @ivar username: The username from the response from the client.
    @type username: L{bytes} or L{None} if not yet provided.
    """

    username = None
    challenge = b""
    response = b""

    def __init__(self, host=None):
        self.host = host

    def getChallenge(self):
        if self.challenge:
            return self.challenge
        # The data encoded in the first ready response contains an
        # presumptively arbitrary string of random digits, a timestamp, and
        # the fully-qualified primary host name of the server.  The syntax of
        # the unencoded form must correspond to that of an RFC 822 'msg-id'
        # [RFC822] as described in [POP3].
        #   -- RFC 2195
        r = random.randrange(0x7FFFFFFF)
        t = time.time()
        self.challenge = networkString(
            "<%d.%d@%s>" % (r, t, nativeString(self.host) if self.host else None)
        )
        return self.challenge

    def setResponse(self, response):
        self.username, self.response = response.split(None, 1)

    def moreChallenges(self):
        return False

    def checkPassword(self, password):
        verify = hexlify(hmac.HMAC(password, self.challenge, digestmod=md5).digest())
        return verify == self.response


@implementer(IUsernameHashedPassword)
class UsernameHashedPassword:

    deprecatedModuleAttribute(
        Version("Twisted", 21, 2, 0),
        "Use twisted.cred.credentials.UsernamePassword instead.",
        "twisted.cred.credentials",
        "UsernameHashedPassword",
    )

    def __init__(self, username, hashed):
        self.username = username
        self.hashed = hashed

    def checkPassword(self, password):
        return self.hashed == password


@implementer(IUsernamePassword)
class UsernamePassword:
    def __init__(self, username, password):
        self.username = username
        self.password = password

    def checkPassword(self, password):
        return self.password == password


@implementer(IAnonymous)
class Anonymous:
    pass


class ISSHPrivateKey(ICredentials):
    """
    L{ISSHPrivateKey} credentials encapsulate an SSH public key to be checked
    against a user's private key.

    @ivar username: The username associated with these credentials.
    @type username: L{bytes}

    @ivar algName: The algorithm name for the blob.
    @type algName: L{bytes}

    @ivar blob: The public key blob as sent by the client.
    @type blob: L{bytes}

    @ivar sigData: The data the signature was made from.
    @type sigData: L{bytes}

    @ivar signature: The signed data.  This is checked to verify that the user
        owns the private key.
    @type signature: L{bytes} or L{None}
    """


@implementer(ISSHPrivateKey)
class SSHPrivateKey:
    def __init__(self, username, algName, blob, sigData, signature):
        self.username = username
        self.algName = algName
        self.blob = blob
        self.sigData = sigData
        self.signature = signature

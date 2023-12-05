# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.cred._digest} and the associated bits in
L{twisted.cred.credentials}.
"""


import base64
from binascii import hexlify
from hashlib import md5, sha1

from zope.interface.verify import verifyObject

from twisted.cred.credentials import (
    DigestCredentialFactory,
    IUsernameDigestHash,
    calcHA1,
    calcHA2,
    calcResponse,
)
from twisted.cred.error import LoginFailed
from twisted.internet.address import IPv4Address
from twisted.python.compat import networkString
from twisted.trial.unittest import TestCase


def b64encode(s):
    return base64.b64encode(s).strip()


class FakeDigestCredentialFactory(DigestCredentialFactory):
    """
    A Fake Digest Credential Factory that generates a predictable
    nonce and opaque
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.privateKey = b"0"

    def _generateNonce(self):
        """
        Generate a static nonce
        """
        return b"178288758716122392881254770685"

    def _getTime(self):
        """
        Return a stable time
        """
        return 0


class DigestAuthTests(TestCase):
    """
    L{TestCase} mixin class which defines a number of tests for
    L{DigestCredentialFactory}.  Because this mixin defines C{setUp}, it
    must be inherited before L{TestCase}.
    """

    def setUp(self):
        """
        Create a DigestCredentialFactory for testing
        """
        self.username = b"foobar"
        self.password = b"bazquux"
        self.realm = b"test realm"
        self.algorithm = b"md5"
        self.cnonce = b"29fc54aa1641c6fa0e151419361c8f23"
        self.qop = b"auth"
        self.uri = b"/write/"
        self.clientAddress = IPv4Address("TCP", "10.2.3.4", 43125)
        self.method = b"GET"
        self.credentialFactory = DigestCredentialFactory(self.algorithm, self.realm)

    def test_MD5HashA1(self, _algorithm=b"md5", _hash=md5):
        """
        L{calcHA1} accepts the C{'md5'} algorithm and returns an MD5 hash of
        its parameters, excluding the nonce and cnonce.
        """
        nonce = b"abc123xyz"
        hashA1 = calcHA1(
            _algorithm, self.username, self.realm, self.password, nonce, self.cnonce
        )
        a1 = b":".join((self.username, self.realm, self.password))
        expected = hexlify(_hash(a1).digest())
        self.assertEqual(hashA1, expected)

    def test_MD5SessionHashA1(self):
        """
        L{calcHA1} accepts the C{'md5-sess'} algorithm and returns an MD5 hash
        of its parameters, including the nonce and cnonce.
        """
        nonce = b"xyz321abc"
        hashA1 = calcHA1(
            b"md5-sess", self.username, self.realm, self.password, nonce, self.cnonce
        )
        a1 = self.username + b":" + self.realm + b":" + self.password
        ha1 = hexlify(md5(a1).digest())
        a1 = ha1 + b":" + nonce + b":" + self.cnonce
        expected = hexlify(md5(a1).digest())
        self.assertEqual(hashA1, expected)

    def test_SHAHashA1(self):
        """
        L{calcHA1} accepts the C{'sha'} algorithm and returns a SHA hash of its
        parameters, excluding the nonce and cnonce.
        """
        self.test_MD5HashA1(b"sha", sha1)

    def test_MD5HashA2Auth(self, _algorithm=b"md5", _hash=md5):
        """
        L{calcHA2} accepts the C{'md5'} algorithm and returns an MD5 hash of
        its arguments, excluding the entity hash for QOP other than
        C{'auth-int'}.
        """
        method = b"GET"
        hashA2 = calcHA2(_algorithm, method, self.uri, b"auth", None)
        a2 = method + b":" + self.uri
        expected = hexlify(_hash(a2).digest())
        self.assertEqual(hashA2, expected)

    def test_MD5HashA2AuthInt(self, _algorithm=b"md5", _hash=md5):
        """
        L{calcHA2} accepts the C{'md5'} algorithm and returns an MD5 hash of
        its arguments, including the entity hash for QOP of C{'auth-int'}.
        """
        method = b"GET"
        hentity = b"foobarbaz"
        hashA2 = calcHA2(_algorithm, method, self.uri, b"auth-int", hentity)
        a2 = method + b":" + self.uri + b":" + hentity
        expected = hexlify(_hash(a2).digest())
        self.assertEqual(hashA2, expected)

    def test_MD5SessHashA2Auth(self):
        """
        L{calcHA2} accepts the C{'md5-sess'} algorithm and QOP of C{'auth'} and
        returns the same value as it does for the C{'md5'} algorithm.
        """
        self.test_MD5HashA2Auth(b"md5-sess")

    def test_MD5SessHashA2AuthInt(self):
        """
        L{calcHA2} accepts the C{'md5-sess'} algorithm and QOP of C{'auth-int'}
        and returns the same value as it does for the C{'md5'} algorithm.
        """
        self.test_MD5HashA2AuthInt(b"md5-sess")

    def test_SHAHashA2Auth(self):
        """
        L{calcHA2} accepts the C{'sha'} algorithm and returns a SHA hash of
        its arguments, excluding the entity hash for QOP other than
        C{'auth-int'}.
        """
        self.test_MD5HashA2Auth(b"sha", sha1)

    def test_SHAHashA2AuthInt(self):
        """
        L{calcHA2} accepts the C{'sha'} algorithm and returns a SHA hash of
        its arguments, including the entity hash for QOP of C{'auth-int'}.
        """
        self.test_MD5HashA2AuthInt(b"sha", sha1)

    def test_MD5HashResponse(self, _algorithm=b"md5", _hash=md5):
        """
        L{calcResponse} accepts the C{'md5'} algorithm and returns an MD5 hash
        of its parameters, excluding the nonce count, client nonce, and QoP
        value if the nonce count and client nonce are L{None}
        """
        hashA1 = b"abc123"
        hashA2 = b"789xyz"
        nonce = b"lmnopq"

        response = hashA1 + b":" + nonce + b":" + hashA2
        expected = hexlify(_hash(response).digest())

        digest = calcResponse(hashA1, hashA2, _algorithm, nonce, None, None, None)
        self.assertEqual(expected, digest)

    def test_MD5SessionHashResponse(self):
        """
        L{calcResponse} accepts the C{'md5-sess'} algorithm and returns an MD5
        hash of its parameters, excluding the nonce count, client nonce, and
        QoP value if the nonce count and client nonce are L{None}
        """
        self.test_MD5HashResponse(b"md5-sess")

    def test_SHAHashResponse(self):
        """
        L{calcResponse} accepts the C{'sha'} algorithm and returns a SHA hash
        of its parameters, excluding the nonce count, client nonce, and QoP
        value if the nonce count and client nonce are L{None}
        """
        self.test_MD5HashResponse(b"sha", sha1)

    def test_MD5HashResponseExtra(self, _algorithm=b"md5", _hash=md5):
        """
        L{calcResponse} accepts the C{'md5'} algorithm and returns an MD5 hash
        of its parameters, including the nonce count, client nonce, and QoP
        value if they are specified.
        """
        hashA1 = b"abc123"
        hashA2 = b"789xyz"
        nonce = b"lmnopq"
        nonceCount = b"00000004"
        clientNonce = b"abcxyz123"
        qop = b"auth"

        response = (
            hashA1
            + b":"
            + nonce
            + b":"
            + nonceCount
            + b":"
            + clientNonce
            + b":"
            + qop
            + b":"
            + hashA2
        )
        expected = hexlify(_hash(response).digest())

        digest = calcResponse(
            hashA1, hashA2, _algorithm, nonce, nonceCount, clientNonce, qop
        )
        self.assertEqual(expected, digest)

    def test_MD5SessionHashResponseExtra(self):
        """
        L{calcResponse} accepts the C{'md5-sess'} algorithm and returns an MD5
        hash of its parameters, including the nonce count, client nonce, and
        QoP value if they are specified.
        """
        self.test_MD5HashResponseExtra(b"md5-sess")

    def test_SHAHashResponseExtra(self):
        """
        L{calcResponse} accepts the C{'sha'} algorithm and returns a SHA hash
        of its parameters, including the nonce count, client nonce, and QoP
        value if they are specified.
        """
        self.test_MD5HashResponseExtra(b"sha", sha1)

    def formatResponse(self, quotes=True, **kw):
        """
        Format all given keyword arguments and their values suitably for use as
        the value of an HTTP header.

        @types quotes: C{bool}
        @param quotes: A flag indicating whether to quote the values of each
            field in the response.

        @param **kw: Keywords and C{bytes} values which will be treated as field
            name/value pairs to include in the result.

        @rtype: C{bytes}
        @return: The given fields formatted for use as an HTTP header value.
        """
        if "username" not in kw:
            kw["username"] = self.username
        if "realm" not in kw:
            kw["realm"] = self.realm
        if "algorithm" not in kw:
            kw["algorithm"] = self.algorithm
        if "qop" not in kw:
            kw["qop"] = self.qop
        if "cnonce" not in kw:
            kw["cnonce"] = self.cnonce
        if "uri" not in kw:
            kw["uri"] = self.uri
        if quotes:
            quote = b'"'
        else:
            quote = b""

        return b", ".join(
            [
                b"".join((networkString(k), b"=", quote, v, quote))
                for (k, v) in kw.items()
                if v is not None
            ]
        )

    def getDigestResponse(self, challenge, ncount):
        """
        Calculate the response for the given challenge
        """
        nonce = challenge.get("nonce")
        algo = challenge.get("algorithm").lower()
        qop = challenge.get("qop")

        ha1 = calcHA1(
            algo, self.username, self.realm, self.password, nonce, self.cnonce
        )
        ha2 = calcHA2(algo, b"GET", self.uri, qop, None)
        expected = calcResponse(ha1, ha2, algo, nonce, ncount, self.cnonce, qop)
        return expected

    def test_response(self, quotes=True):
        """
        L{DigestCredentialFactory.decode} accepts a digest challenge response
        and parses it into an L{IUsernameHashedPassword} provider.
        """
        challenge = self.credentialFactory.getChallenge(self.clientAddress.host)

        nc = b"00000001"
        clientResponse = self.formatResponse(
            quotes=quotes,
            nonce=challenge["nonce"],
            response=self.getDigestResponse(challenge, nc),
            nc=nc,
            opaque=challenge["opaque"],
        )
        creds = self.credentialFactory.decode(
            clientResponse, self.method, self.clientAddress.host
        )
        self.assertTrue(creds.checkPassword(self.password))
        self.assertFalse(creds.checkPassword(self.password + b"wrong"))

    def test_responseWithoutQuotes(self):
        """
        L{DigestCredentialFactory.decode} accepts a digest challenge response
        which does not quote the values of its fields and parses it into an
        L{IUsernameHashedPassword} provider in the same way it would a
        response which included quoted field values.
        """
        self.test_response(False)

    def test_responseWithCommaURI(self):
        """
        L{DigestCredentialFactory.decode} accepts a digest challenge response
        which quotes the values of its fields and includes a C{b","} in the URI
        field.
        """
        self.uri = b"/some,path/"
        self.test_response(True)

    def test_caseInsensitiveAlgorithm(self):
        """
        The case of the algorithm value in the response is ignored when
        checking the credentials.
        """
        self.algorithm = b"MD5"
        self.test_response()

    def test_md5DefaultAlgorithm(self):
        """
        The algorithm defaults to MD5 if it is not supplied in the response.
        """
        self.algorithm = None
        self.test_response()

    def test_responseWithoutClientIP(self):
        """
        L{DigestCredentialFactory.decode} accepts a digest challenge response
        even if the client address it is passed is L{None}.
        """
        challenge = self.credentialFactory.getChallenge(None)

        nc = b"00000001"
        clientResponse = self.formatResponse(
            nonce=challenge["nonce"],
            response=self.getDigestResponse(challenge, nc),
            nc=nc,
            opaque=challenge["opaque"],
        )
        creds = self.credentialFactory.decode(clientResponse, self.method, None)
        self.assertTrue(creds.checkPassword(self.password))
        self.assertFalse(creds.checkPassword(self.password + b"wrong"))

    def test_multiResponse(self):
        """
        L{DigestCredentialFactory.decode} handles multiple responses to a
        single challenge.
        """
        challenge = self.credentialFactory.getChallenge(self.clientAddress.host)

        nc = b"00000001"
        clientResponse = self.formatResponse(
            nonce=challenge["nonce"],
            response=self.getDigestResponse(challenge, nc),
            nc=nc,
            opaque=challenge["opaque"],
        )

        creds = self.credentialFactory.decode(
            clientResponse, self.method, self.clientAddress.host
        )
        self.assertTrue(creds.checkPassword(self.password))
        self.assertFalse(creds.checkPassword(self.password + b"wrong"))

        nc = b"00000002"
        clientResponse = self.formatResponse(
            nonce=challenge["nonce"],
            response=self.getDigestResponse(challenge, nc),
            nc=nc,
            opaque=challenge["opaque"],
        )

        creds = self.credentialFactory.decode(
            clientResponse, self.method, self.clientAddress.host
        )
        self.assertTrue(creds.checkPassword(self.password))
        self.assertFalse(creds.checkPassword(self.password + b"wrong"))

    def test_failsWithDifferentMethod(self):
        """
        L{DigestCredentialFactory.decode} returns an L{IUsernameHashedPassword}
        provider which rejects a correct password for the given user if the
        challenge response request is made using a different HTTP method than
        was used to request the initial challenge.
        """
        challenge = self.credentialFactory.getChallenge(self.clientAddress.host)

        nc = b"00000001"
        clientResponse = self.formatResponse(
            nonce=challenge["nonce"],
            response=self.getDigestResponse(challenge, nc),
            nc=nc,
            opaque=challenge["opaque"],
        )
        creds = self.credentialFactory.decode(
            clientResponse, b"POST", self.clientAddress.host
        )
        self.assertFalse(creds.checkPassword(self.password))
        self.assertFalse(creds.checkPassword(self.password + b"wrong"))

    def test_noUsername(self):
        """
        L{DigestCredentialFactory.decode} raises L{LoginFailed} if the response
        has no username field or if the username field is empty.
        """
        # Check for no username
        e = self.assertRaises(
            LoginFailed,
            self.credentialFactory.decode,
            self.formatResponse(username=None),
            self.method,
            self.clientAddress.host,
        )
        self.assertEqual(str(e), "Invalid response, no username given.")

        # Check for an empty username
        e = self.assertRaises(
            LoginFailed,
            self.credentialFactory.decode,
            self.formatResponse(username=b""),
            self.method,
            self.clientAddress.host,
        )
        self.assertEqual(str(e), "Invalid response, no username given.")

    def test_noNonce(self):
        """
        L{DigestCredentialFactory.decode} raises L{LoginFailed} if the response
        has no nonce.
        """
        e = self.assertRaises(
            LoginFailed,
            self.credentialFactory.decode,
            self.formatResponse(opaque=b"abc123"),
            self.method,
            self.clientAddress.host,
        )
        self.assertEqual(str(e), "Invalid response, no nonce given.")

    def test_noOpaque(self):
        """
        L{DigestCredentialFactory.decode} raises L{LoginFailed} if the response
        has no opaque.
        """
        e = self.assertRaises(
            LoginFailed,
            self.credentialFactory.decode,
            self.formatResponse(),
            self.method,
            self.clientAddress.host,
        )
        self.assertEqual(str(e), "Invalid response, no opaque given.")

    def test_checkHash(self):
        """
        L{DigestCredentialFactory.decode} returns an L{IUsernameDigestHash}
        provider which can verify a hash of the form 'username:realm:password'.
        """
        challenge = self.credentialFactory.getChallenge(self.clientAddress.host)

        nc = b"00000001"
        clientResponse = self.formatResponse(
            nonce=challenge["nonce"],
            response=self.getDigestResponse(challenge, nc),
            nc=nc,
            opaque=challenge["opaque"],
        )

        creds = self.credentialFactory.decode(
            clientResponse, self.method, self.clientAddress.host
        )
        self.assertTrue(verifyObject(IUsernameDigestHash, creds))

        cleartext = self.username + b":" + self.realm + b":" + self.password
        hash = md5(cleartext)
        self.assertTrue(creds.checkHash(hexlify(hash.digest())))
        hash.update(b"wrong")
        self.assertFalse(creds.checkHash(hexlify(hash.digest())))

    def test_invalidOpaque(self):
        """
        L{DigestCredentialFactory.decode} raises L{LoginFailed} when the opaque
        value does not contain all the required parts.
        """
        credentialFactory = FakeDigestCredentialFactory(self.algorithm, self.realm)
        challenge = credentialFactory.getChallenge(self.clientAddress.host)

        exc = self.assertRaises(
            LoginFailed,
            credentialFactory._verifyOpaque,
            b"badOpaque",
            challenge["nonce"],
            self.clientAddress.host,
        )
        self.assertEqual(str(exc), "Invalid response, invalid opaque value")

        badOpaque = b"foo-" + b64encode(b"nonce,clientip")

        exc = self.assertRaises(
            LoginFailed,
            credentialFactory._verifyOpaque,
            badOpaque,
            challenge["nonce"],
            self.clientAddress.host,
        )
        self.assertEqual(str(exc), "Invalid response, invalid opaque value")

        exc = self.assertRaises(
            LoginFailed,
            credentialFactory._verifyOpaque,
            b"",
            challenge["nonce"],
            self.clientAddress.host,
        )
        self.assertEqual(str(exc), "Invalid response, invalid opaque value")

        badOpaque = b"foo-" + b64encode(
            b",".join(
                (challenge["nonce"], networkString(self.clientAddress.host), b"foobar")
            )
        )
        exc = self.assertRaises(
            LoginFailed,
            credentialFactory._verifyOpaque,
            badOpaque,
            challenge["nonce"],
            self.clientAddress.host,
        )
        self.assertEqual(str(exc), "Invalid response, invalid opaque/time values")

    def test_incompatibleNonce(self):
        """
        L{DigestCredentialFactory.decode} raises L{LoginFailed} when the given
        nonce from the response does not match the nonce encoded in the opaque.
        """
        credentialFactory = FakeDigestCredentialFactory(self.algorithm, self.realm)
        challenge = credentialFactory.getChallenge(self.clientAddress.host)

        badNonceOpaque = credentialFactory._generateOpaque(
            b"1234567890", self.clientAddress.host
        )

        exc = self.assertRaises(
            LoginFailed,
            credentialFactory._verifyOpaque,
            badNonceOpaque,
            challenge["nonce"],
            self.clientAddress.host,
        )
        self.assertEqual(str(exc), "Invalid response, incompatible opaque/nonce values")

        exc = self.assertRaises(
            LoginFailed,
            credentialFactory._verifyOpaque,
            badNonceOpaque,
            b"",
            self.clientAddress.host,
        )
        self.assertEqual(str(exc), "Invalid response, incompatible opaque/nonce values")

    def test_incompatibleClientIP(self):
        """
        L{DigestCredentialFactory.decode} raises L{LoginFailed} when the
        request comes from a client IP other than what is encoded in the
        opaque.
        """
        credentialFactory = FakeDigestCredentialFactory(self.algorithm, self.realm)
        challenge = credentialFactory.getChallenge(self.clientAddress.host)

        badAddress = "10.0.0.1"
        # Sanity check
        self.assertNotEqual(self.clientAddress.host, badAddress)

        badNonceOpaque = credentialFactory._generateOpaque(
            challenge["nonce"], badAddress
        )

        self.assertRaises(
            LoginFailed,
            credentialFactory._verifyOpaque,
            badNonceOpaque,
            challenge["nonce"],
            self.clientAddress.host,
        )

    def test_oldNonce(self):
        """
        L{DigestCredentialFactory.decode} raises L{LoginFailed} when the given
        opaque is older than C{DigestCredentialFactory.CHALLENGE_LIFETIME_SECS}
        """
        credentialFactory = FakeDigestCredentialFactory(self.algorithm, self.realm)
        challenge = credentialFactory.getChallenge(self.clientAddress.host)

        key = b",".join(
            (challenge["nonce"], networkString(self.clientAddress.host), b"-137876876")
        )
        digest = hexlify(md5(key + credentialFactory.privateKey).digest())
        ekey = b64encode(key)

        oldNonceOpaque = b"-".join((digest, ekey.strip(b"\n")))

        self.assertRaises(
            LoginFailed,
            credentialFactory._verifyOpaque,
            oldNonceOpaque,
            challenge["nonce"],
            self.clientAddress.host,
        )

    def test_mismatchedOpaqueChecksum(self):
        """
        L{DigestCredentialFactory.decode} raises L{LoginFailed} when the opaque
        checksum fails verification.
        """
        credentialFactory = FakeDigestCredentialFactory(self.algorithm, self.realm)
        challenge = credentialFactory.getChallenge(self.clientAddress.host)

        key = b",".join(
            (challenge["nonce"], networkString(self.clientAddress.host), b"0")
        )

        digest = hexlify(md5(key + b"this is not the right pkey").digest())
        badChecksum = b"-".join((digest, b64encode(key)))

        self.assertRaises(
            LoginFailed,
            credentialFactory._verifyOpaque,
            badChecksum,
            challenge["nonce"],
            self.clientAddress.host,
        )

    def test_incompatibleCalcHA1Options(self):
        """
        L{calcHA1} raises L{TypeError} when any of the pszUsername, pszRealm,
        or pszPassword arguments are specified with the preHA1 keyword
        argument.
        """
        arguments = (
            (b"user", b"realm", b"password", b"preHA1"),
            (None, b"realm", None, b"preHA1"),
            (None, None, b"password", b"preHA1"),
        )

        for pszUsername, pszRealm, pszPassword, preHA1 in arguments:
            self.assertRaises(
                TypeError,
                calcHA1,
                b"md5",
                pszUsername,
                pszRealm,
                pszPassword,
                b"nonce",
                b"cnonce",
                preHA1=preHA1,
            )

    def test_noNewlineOpaque(self):
        """
        L{DigestCredentialFactory._generateOpaque} returns a value without
        newlines, regardless of the length of the nonce.
        """
        opaque = self.credentialFactory._generateOpaque(b"long nonce " * 10, None)
        self.assertNotIn(b"\n", opaque)

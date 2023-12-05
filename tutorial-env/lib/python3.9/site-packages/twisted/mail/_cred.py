# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Credential managers for L{twisted.mail}.
"""


import hashlib
import hmac

from zope.interface import implementer

from twisted.cred import credentials
from twisted.mail._except import IllegalClientResponse
from twisted.mail.interfaces import IChallengeResponse, IClientAuthentication
from twisted.python.compat import nativeString


@implementer(IClientAuthentication)
class CramMD5ClientAuthenticator:
    def __init__(self, user):
        self.user = user

    def getName(self):
        return b"CRAM-MD5"

    def challengeResponse(self, secret, chal):
        response = hmac.HMAC(secret, chal, digestmod=hashlib.md5).hexdigest()
        return self.user + b" " + response.encode("ascii")


@implementer(IClientAuthentication)
class LOGINAuthenticator:
    def __init__(self, user):
        self.user = user
        self.challengeResponse = self.challengeUsername

    def getName(self):
        return b"LOGIN"

    def challengeUsername(self, secret, chal):
        # Respond to something like "Username:"
        self.challengeResponse = self.challengeSecret
        return self.user

    def challengeSecret(self, secret, chal):
        # Respond to something like "Password:"
        return secret


@implementer(IClientAuthentication)
class PLAINAuthenticator:
    def __init__(self, user):
        self.user = user

    def getName(self):
        return b"PLAIN"

    def challengeResponse(self, secret, chal):
        return b"\0" + self.user + b"\0" + secret


@implementer(IChallengeResponse)
class LOGINCredentials(credentials.UsernamePassword):
    def __init__(self):
        self.challenges = [b"Password\0", b"User Name\0"]
        self.responses = [b"password", b"username"]
        credentials.UsernamePassword.__init__(self, None, None)

    def getChallenge(self):
        return self.challenges.pop()

    def setResponse(self, response):
        setattr(self, nativeString(self.responses.pop()), response)

    def moreChallenges(self):
        return bool(self.challenges)


@implementer(IChallengeResponse)
class PLAINCredentials(credentials.UsernamePassword):
    def __init__(self):
        credentials.UsernamePassword.__init__(self, None, None)

    def getChallenge(self):
        return b""

    def setResponse(self, response):
        parts = response.split(b"\0")
        if len(parts) != 3:
            raise IllegalClientResponse("Malformed Response - wrong number of parts")
        useless, self.username, self.password = parts

    def moreChallenges(self):
        return False


__all__ = [
    "CramMD5ClientAuthenticator",
    "LOGINCredentials",
    "LOGINAuthenticator",
    "PLAINCredentials",
    "PLAINAuthenticator",
]

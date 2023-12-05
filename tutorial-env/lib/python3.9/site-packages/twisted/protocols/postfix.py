# -*- test-case-name: twisted.test.test_postfix -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Postfix mail transport agent related protocols.
"""

import sys
from collections import UserDict
from urllib.parse import quote as _quote, unquote as _unquote

from twisted.internet import defer, protocol
from twisted.protocols import basic, policies
from twisted.python import log


# urllib's quote functions just happen to match
# the postfix semantics.
def quote(s):
    quoted = _quote(s)
    if isinstance(quoted, str):
        quoted = quoted.encode("ascii")
    return quoted


def unquote(s):
    if isinstance(s, bytes):
        s = s.decode("ascii")
    quoted = _unquote(s)
    return quoted.encode("ascii")


class PostfixTCPMapServer(basic.LineReceiver, policies.TimeoutMixin):
    """
    Postfix mail transport agent TCP map protocol implementation.

    Receive requests for data matching given key via lineReceived,
    asks it's factory for the data with self.factory.get(key), and
    returns the data to the requester. None means no entry found.

    You can use postfix's postmap to test the map service::

    /usr/sbin/postmap -q KEY tcp:localhost:4242

    """

    timeout = 600
    delimiter = b"\n"

    def connectionMade(self):
        self.setTimeout(self.timeout)

    def sendCode(self, code, message=b""):
        """
        Send an SMTP-like code with a message.
        """
        self.sendLine(str(code).encode("ascii") + b" " + message)

    def lineReceived(self, line):
        self.resetTimeout()
        try:
            request, params = line.split(None, 1)
        except ValueError:
            request = line
            params = None
        try:
            f = getattr(self, "do_" + request.decode("ascii"))
        except AttributeError:
            self.sendCode(400, b"unknown command")
        else:
            try:
                f(params)
            except BaseException:
                excInfo = str(sys.exc_info()[1]).encode("ascii")
                self.sendCode(400, b"Command " + request + b" failed: " + excInfo)

    def do_get(self, key):
        if key is None:
            self.sendCode(400, b"Command 'get' takes 1 parameters.")
        else:
            d = defer.maybeDeferred(self.factory.get, key)
            d.addCallbacks(self._cbGot, self._cbNot)
            d.addErrback(log.err)

    def _cbNot(self, fail):
        msg = fail.getErrorMessage().encode("ascii")
        self.sendCode(400, msg)

    def _cbGot(self, value):
        if value is None:
            self.sendCode(500)
        else:
            self.sendCode(200, quote(value))

    def do_put(self, keyAndValue):
        if keyAndValue is None:
            self.sendCode(400, b"Command 'put' takes 2 parameters.")
        else:
            try:
                key, value = keyAndValue.split(None, 1)
            except ValueError:
                self.sendCode(400, b"Command 'put' takes 2 parameters.")
            else:
                self.sendCode(500, b"put is not implemented yet.")


class PostfixTCPMapDictServerFactory(UserDict, protocol.ServerFactory):
    """
    An in-memory dictionary factory for PostfixTCPMapServer.
    """

    protocol = PostfixTCPMapServer


class PostfixTCPMapDeferringDictServerFactory(protocol.ServerFactory):
    """
    An in-memory dictionary factory for PostfixTCPMapServer.
    """

    protocol = PostfixTCPMapServer

    def __init__(self, data=None):
        self.data = {}
        if data is not None:
            self.data.update(data)

    def get(self, key):
        return defer.succeed(self.data.get(key))

# -*- test-case-name: twisted.test.test_postfix -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Postfix mail transport agent related protocols.
"""

import sys
try:
    # Python 2
    from UserDict import UserDict
except ImportError:
    # Python 3
    from collections import UserDict

try:
    # Python 2
    from urllib import quote as _quote, unquote as _unquote
except ImportError:
    # Python 3
    from urllib.parse import quote as _quote, unquote as _unquote

from twisted.protocols import basic
from twisted.protocols import policies
from twisted.internet import protocol, defer
from twisted.python import log
from twisted.python.compat import intToBytes, nativeString, networkString

# urllib's quote functions just happen to match
# the postfix semantics.
def quote(s):
    return networkString(_quote(s))



def unquote(s):
    return networkString(_unquote(nativeString(s)))



class PostfixTCPMapServer(basic.LineReceiver, policies.TimeoutMixin):
    """Postfix mail transport agent TCP map protocol implementation.

    Receive requests for data matching given key via lineReceived,
    asks it's factory for the data with self.factory.get(key), and
    returns the data to the requester. None means no entry found.

    You can use postfix's postmap to test the map service::

    /usr/sbin/postmap -q KEY tcp:localhost:4242

    """

    timeout = 600
    delimiter = b'\n'

    def connectionMade(self):
        self.setTimeout(self.timeout)



    def sendCode(self, code, message=b''):
        """
        Send an SMTP-like code with a message.
        """
        self.sendLine(intToBytes(code) + b' ' + message)



    def lineReceived(self, line):
        self.resetTimeout()
        try:
            request, params = line.split(None, 1)
        except ValueError:
            request = line
            params = None
        try:
            f = getattr(self, 'do_' + nativeString(request))
        except AttributeError:
            self.sendCode(400, b'unknown command')
        else:
            try:
                f(params)
            except:
                self.sendCode(400, b'Command ' + request + b' failed: ' +
                              networkString(str(sys.exc_info()[1])))



    def do_get(self, key):
        if key is None:
            self.sendCode(400, b"Command 'get' takes 1 parameters.")
        else:
            d = defer.maybeDeferred(self.factory.get, key)
            d.addCallbacks(self._cbGot, self._cbNot)
            d.addErrback(log.err)



    def _cbNot(self, fail):
        self.sendCode(400, fail.getErrorMessage())



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
                self.sendCode(500, b'put is not implemented yet.')




class PostfixTCPMapDictServerFactory(protocol.ServerFactory,
                                     UserDict):
    """An in-memory dictionary factory for PostfixTCPMapServer."""

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

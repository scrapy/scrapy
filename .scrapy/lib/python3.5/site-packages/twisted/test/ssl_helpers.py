# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Helper classes for twisted.test.test_ssl.

They are in a separate module so they will not prevent test_ssl importing if
pyOpenSSL is unavailable.
"""
from __future__ import division, absolute_import

from twisted.python.compat import nativeString
from twisted.internet import ssl
from twisted.python.filepath import FilePath

from OpenSSL import SSL

certPath = nativeString(FilePath(__file__.encode("utf-8")
                    ).sibling(b"server.pem").path)


class ClientTLSContext(ssl.ClientContextFactory):
    isClient = 1
    def getContext(self):
        return SSL.Context(SSL.TLSv1_METHOD)

class ServerTLSContext:
    isClient = 0

    def __init__(self, filename=certPath, method=SSL.TLSv1_METHOD):
        self.filename = filename
        self._method = method

    def getContext(self):
        ctx = SSL.Context(self._method)
        ctx.use_certificate_file(self.filename)
        ctx.use_privatekey_file(self.filename)
        return ctx

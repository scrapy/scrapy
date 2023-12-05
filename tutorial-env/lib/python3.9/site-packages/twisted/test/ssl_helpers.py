# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Helper classes for twisted.test.test_ssl.

They are in a separate module so they will not prevent test_ssl importing if
pyOpenSSL is unavailable.
"""

from OpenSSL import SSL

from twisted.internet import ssl
from twisted.python.compat import nativeString
from twisted.python.filepath import FilePath

certPath = nativeString(FilePath(__file__.encode("utf-8")).sibling(b"server.pem").path)


class ClientTLSContext(ssl.ClientContextFactory):
    """
    SSL Context Factory for client-side connections.
    """

    isClient = 1

    def getContext(self):
        """
        Return an L{SSL.Context} to be use for client-side connections.

        Will not return a cached context.
        This is done to improve the test coverage as most implementation
        are caching the context.
        """
        return SSL.Context(SSL.SSLv23_METHOD)


class ServerTLSContext:
    """
    SSL Context Factory for server-side connections.
    """

    isClient = 0

    def __init__(self, filename=certPath, method=None):
        self.filename = filename
        if method is None:
            method = SSL.SSLv23_METHOD

        self._method = method

    def getContext(self):
        """
        Return an L{SSL.Context} to be use for server-side connections.

        Will not return a cached context.
        This is done to improve the test coverage as most implementation
        are caching the context.
        """
        ctx = SSL.Context(self._method)
        ctx.use_certificate_file(self.filename)
        ctx.use_privatekey_file(self.filename)
        return ctx

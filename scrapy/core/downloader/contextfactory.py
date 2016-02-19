from OpenSSL import SSL
from twisted.internet.ssl import ClientContextFactory

from scrapy import twisted_version

if twisted_version >= (14, 0, 0):

    from zope.interface.declarations import implementer

    from twisted.internet.ssl import optionsForClientTLS
    from twisted.web.client import BrowserLikePolicyForHTTPS
    from twisted.web.iweb import IPolicyForHTTPS

    @implementer(IPolicyForHTTPS)
    class ScrapyClientContextFactory(BrowserLikePolicyForHTTPS):
        """
        Using Twisted recommended context factory for twisted.web.client.Agent

        Quoting:
        "The default is to use a BrowserLikePolicyForHTTPS,
        so unless you have special requirements you can leave this as-is."

        See http://twistedmatrix.com/documents/current/api/twisted.web.client.Agent.html
        """


    @implementer(IPolicyForHTTPS)
    class OpenSSLMethodContextFactory(ScrapyClientContextFactory):

        openssl_method = SSL.SSLv23_METHOD

        def creatorForNetloc(self, hostname, port):
            return optionsForClientTLS(hostname.decode("ascii"),
                                       trustRoot=self._trustRoot,
                                       extraCertificateOptions={
                                            'method': self.openssl_method
                                       })


else:

    class OpenSSLMethodContextFactory(ClientContextFactory):
        "A SSL context factory which is more permissive against SSL bugs."
        # see https://github.com/scrapy/scrapy/issues/82
        # and https://github.com/scrapy/scrapy/issues/26
        # and https://github.com/scrapy/scrapy/issues/981
        openssl_method = SSL.SSLv23_METHOD

        def __init__(self):
            self.method = self.openssl_method

        def getContext(self, hostname=None, port=None):
            ctx = ClientContextFactory.getContext(self)
            # Enable all workarounds to SSL bugs as documented by
            # http://www.openssl.org/docs/ssl/SSL_CTX_set_options.html
            ctx.set_options(SSL.OP_ALL)
            if hostname and ClientTLSOptions is not None: # workaround for TLS SNI
                ClientTLSOptions(hostname, ctx)
            return ctx

    ScrapyClientContextFactory = OpenSSLMethodContextFactory


class SSLv3ContextFactory(OpenSSLMethodContextFactory):
    openssl_method = SSL.SSLv3_METHOD


class TLSv1ContextFactory(OpenSSLMethodContextFactory):
    openssl_method = SSL.TLSv1_METHOD

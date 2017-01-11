from OpenSSL import SSL
from twisted.internet.ssl import ClientContextFactory

try:

    from zope.interface.declarations import implementer

    # the following should be available from Twisted 14.0.0
    from twisted.internet.ssl import (optionsForClientTLS,
                                      CertificateOptions,
                                      platformTrust)

    from twisted.web.client import BrowserLikePolicyForHTTPS
    from twisted.web.iweb import IPolicyForHTTPS

    from scrapy.core.downloader.tls import ScrapyClientTLSOptions, DEFAULT_CIPHERS


    @implementer(IPolicyForHTTPS)
    class ScrapyClientContextFactory(BrowserLikePolicyForHTTPS):
        """
        Non-peer-certificate verifying HTTPS context factory

        Default OpenSSL method is TLS_METHOD (also called SSLv23_METHOD)
        which allows TLS protocol negotiation

        'A TLS/SSL connection established with [this method] may
         understand the SSLv3, TLSv1, TLSv1.1 and TLSv1.2 protocols.'
        """

        def __init__(self, method=SSL.SSLv23_METHOD, *args, **kwargs):
            super(ScrapyClientContextFactory, self).__init__(*args, **kwargs)
            self._ssl_method = method

        def getCertificateOptions(self):
            # setting verify=True will require you to provide CAs
            # to verify against; in other words: it's not that simple

            # backward-compatible SSL/TLS method:
            #
            # * this will respect `method` attribute in often recommended
            #   `ScrapyClientContextFactory` subclass
            #   (https://github.com/scrapy/scrapy/issues/1429#issuecomment-131782133)
            #
            # * getattr() for `_ssl_method` attribute for context factories
            #   not calling super(..., self).__init__
            return CertificateOptions(verify=False,
                        method=getattr(self, 'method',
                                       getattr(self, '_ssl_method', None)),
                        fixBrokenPeers=True,
                        acceptableCiphers=DEFAULT_CIPHERS)

        # kept for old-style HTTP/1.0 downloader context twisted calls,
        # e.g. connectSSL()
        def getContext(self, hostname=None, port=None):
            return self.getCertificateOptions().getContext()

        def creatorForNetloc(self, hostname, port):
            return ScrapyClientTLSOptions(hostname.decode("ascii"), self.getContext())


    @implementer(IPolicyForHTTPS)
    class BrowserLikeContextFactory(ScrapyClientContextFactory):
        """
        Twisted-recommended context factory for web clients.

        Quoting http://twistedmatrix.com/documents/current/api/twisted.web.client.Agent.html:
        "The default is to use a BrowserLikePolicyForHTTPS,
        so unless you have special requirements you can leave this as-is."

        creatorForNetloc() is the same as BrowserLikePolicyForHTTPS
        except this context factory allows setting the TLS/SSL method to use.

        Default OpenSSL method is TLS_METHOD (also called SSLv23_METHOD)
        which allows TLS protocol negotiation.
        """
        def creatorForNetloc(self, hostname, port):

            # trustRoot set to platformTrust() will use the platform's root CAs.
            #
            # This means that a website like https://www.cacert.org will be rejected
            # by default, since CAcert.org CA certificate is seldom shipped.
            return optionsForClientTLS(hostname.decode("ascii"),
                                       trustRoot=platformTrust(),
                                       extraCertificateOptions={
                                            'method': self._ssl_method,
                                       })

except ImportError:

    class ScrapyClientContextFactory(ClientContextFactory):
        "A SSL context factory which is more permissive against SSL bugs."
        # see https://github.com/scrapy/scrapy/issues/82
        # and https://github.com/scrapy/scrapy/issues/26
        # and https://github.com/scrapy/scrapy/issues/981

        def __init__(self, method=SSL.SSLv23_METHOD):
            self.method = method

        def getContext(self, hostname=None, port=None):
            ctx = ClientContextFactory.getContext(self)
            # Enable all workarounds to SSL bugs as documented by
            # http://www.openssl.org/docs/ssl/SSL_CTX_set_options.html
            ctx.set_options(SSL.OP_ALL)
            return ctx

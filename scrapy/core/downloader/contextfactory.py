from OpenSSL import SSL
from twisted.internet.ssl import ClientContextFactory

from scrapy import twisted_version

if twisted_version >= (14, 0, 0):
    from twisted.internet.ssl import CertificateOptions
    from twisted.internet._sslverify import ClientTLSOptions
    from twisted.web.iweb import IPolicyForHTTPS
    from zope.interface import implementer

    class ScrapyOpenSSLCertificateOptions(CertificateOptions):
        # we need to subclass CertificateOptions because there's no way to
        # update SSL context in ScrapyClientContextFactory or
        # twisted.internet.ssl.optionsForClientTLS

        def __init__(self, **kwargs):
            super(ScrapyOpenSSLCertificateOptions, self).__init__(**kwargs)
            self.method = SSL.TLSv1_METHOD

        def getContext(self):
            ctx = super(ScrapyOpenSSLCertificateOptions, self).getContext()
            ctx.set_options(SSL.OP_ALL)
            return ctx


    @implementer(IPolicyForHTTPS)
    class ScrapyClientContextFactory(object):

        def creatorForNetloc(self, hostname, port):
            certificateOptions = ScrapyOpenSSLCertificateOptions()
            return ClientTLSOptions(
                hostname.decode('utf-8'), certificateOptions.getContext()
            )

else:

    class ScrapyClientContextFactory(ClientContextFactory):
        "A SSL context factory which is more permissive against SSL bugs."
        # see https://github.com/scrapy/scrapy/issues/82
        # and https://github.com/scrapy/scrapy/issues/26

        def __init__(self):
            # see this issue on why we use TLSv1_METHOD by default
            # https://github.com/scrapy/scrapy/issues/194
            self.method = SSL.TLSv1_METHOD

        def getContext(self, hostname=None, port=None):
            ctx = ClientContextFactory.getContext(self)
            # Enable all workarounds to SSL bugs as documented by
            # http://www.openssl.org/docs/ssl/SSL_CTX_set_options.html
            ctx.set_options(SSL.OP_ALL)
            return ctx

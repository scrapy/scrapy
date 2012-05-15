from OpenSSL import SSL
from twisted.internet.ssl import ClientContextFactory


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

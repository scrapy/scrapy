from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from OpenSSL import SSL
from twisted.internet import ssl

from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from twisted.internet.ssl import ContextFactory


def ssl_context_factory(
    keyfile: str = "keys/localhost.key",
    certfile: str = "keys/localhost.crt",
    cipher_string: str | None = None,
) -> ContextFactory:
    factory = ssl.DefaultOpenSSLContextFactory(
        str(Path(__file__).parent.parent / keyfile),
        str(Path(__file__).parent.parent / certfile),
    )
    if cipher_string:
        ctx = factory.getContext()
        # disabling TLS1.3 because it unconditionally enables some strong ciphers
        ctx.set_options(SSL.OP_CIPHER_SERVER_PREFERENCE | SSL.OP_NO_TLSv1_3)
        ctx.set_cipher_list(to_bytes(cipher_string))
    return factory

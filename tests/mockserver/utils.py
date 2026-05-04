from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import load_pem_x509_certificate
from OpenSSL import SSL
from OpenSSL.crypto import FILETYPE_PEM, load_certificate, load_privatekey
from twisted.internet.ssl import CertificateOptions

from scrapy.utils._deps_compat import PYOPENSSL_WANTS_X509_PKEY
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from twisted.internet.interfaces import IOpenSSLContextFactory


def ssl_context_factory(
    keyfile: str = "keys/localhost.key",
    certfile: str = "keys/localhost.crt",
    cipher_string: str | None = None,
) -> IOpenSSLContextFactory:
    keyfile_path = Path(__file__).parent.parent / keyfile
    certfile_path = Path(__file__).parent.parent / certfile

    if not PYOPENSSL_WANTS_X509_PKEY:
        cert = load_pem_x509_certificate(certfile_path.read_bytes())
        key = load_pem_private_key(keyfile_path.read_bytes(), password=None)
    else:
        cert = load_certificate(FILETYPE_PEM, certfile_path.read_bytes())  # type: ignore[assignment]
        key = load_privatekey(FILETYPE_PEM, keyfile_path.read_bytes())  # type: ignore[assignment]

    factory: CertificateOptions = CertificateOptions(
        privateKey=key,
        certificate=cert,
    )
    if cipher_string:
        ctx = factory.getContext()
        # disabling TLS1.3 because it unconditionally enables some strong ciphers
        ctx.set_options(SSL.OP_CIPHER_SERVER_PREFERENCE | SSL.OP_NO_TLSv1_3)
        ctx.set_cipher_list(to_bytes(cipher_string))
    return factory

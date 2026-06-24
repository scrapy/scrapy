from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import load_pem_x509_certificate
from OpenSSL import SSL
from OpenSSL.crypto import FILETYPE_PEM, load_certificate, load_privatekey
from twisted.internet.ssl import CertificateOptions, ContextFactory

from scrapy.core.downloader.tls import _TWISTED_VERSION_MAP
from scrapy.utils._deps_compat import PYOPENSSL_X509_DEPRECATED
from scrapy.utils.python import to_bytes
from scrapy.utils.ssl import _get_cert_options_version_kwargs

if TYPE_CHECKING:
    from twisted.internet.interfaces import IOpenSSLContextFactory


def ssl_context_factory(
    keyfile: str = "keys/localhost.key",
    certfile: str = "keys/localhost.crt",
    *,
    cipher_string: str | None = None,
    tls_min_version: str | None = None,
    tls_max_version: str | None = None,
) -> IOpenSSLContextFactory:
    keyfile_path = Path(__file__).parent.parent / keyfile
    certfile_path = Path(__file__).parent.parent / certfile

    if PYOPENSSL_X509_DEPRECATED:
        cert = load_pem_x509_certificate(certfile_path.read_bytes())
        key = load_pem_private_key(keyfile_path.read_bytes(), password=None)
    else:
        cert = load_certificate(FILETYPE_PEM, certfile_path.read_bytes())  # type: ignore[assignment]
        key = load_privatekey(FILETYPE_PEM, keyfile_path.read_bytes())  # type: ignore[assignment]

    tls_min = _TWISTED_VERSION_MAP.get(tls_min_version) if tls_min_version else None
    tls_max = _TWISTED_VERSION_MAP.get(tls_max_version) if tls_max_version else None
    tls_version_kwargs = _get_cert_options_version_kwargs(tls_min, tls_max)
    # https://github.com/twisted/twisted/issues/12638
    factory: CertificateOptions = CertificateOptions(
        privateKey=key,  # type: ignore[arg-type]
        certificate=cert,  # type: ignore[arg-type]
        **tls_version_kwargs,
    )
    if cipher_string:
        ctx = factory.getContext()
        # disabling TLS1.3 because it unconditionally enables some strong ciphers
        ctx.set_options(SSL.OP_CIPHER_SERVER_PREFERENCE | SSL.OP_NO_TLSv1_3)
        ctx.set_cipher_list(to_bytes(cipher_string))
    return cast("ContextFactory", factory)

# pragma: no file cover
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

import OpenSSL._util as pyOpenSSLutil

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._versions import _get_openssl_version as get_openssl_version
from scrapy.utils.python import to_unicode

if TYPE_CHECKING:
    from OpenSSL.crypto import X509Name


def get_temp_key_info(ssl_object: Any) -> str | None:
    # A no-op: it read the negotiated ephemeral key through a binding that
    # cryptography 40.0.0 removed.
    return None


def ffi_buf_to_string(buf: Any) -> str:
    return to_unicode(pyOpenSSLutil.ffi.string(buf))


def x509name_to_string(x509name: X509Name) -> str:
    # from OpenSSL.crypto.X509Name.__repr__
    result_buffer: Any = pyOpenSSLutil.ffi.new("char[]", 512)
    pyOpenSSLutil.lib.X509_NAME_oneline(
        x509name._name, result_buffer, len(result_buffer)
    )
    return ffi_buf_to_string(result_buffer)


warnings.warn(
    "The scrapy.utils.ssl module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ffi_buf_to_string",
    "get_openssl_version",
    "get_temp_key_info",
    "x509name_to_string",
]

from __future__ import annotations

import logging
import ssl
import warnings
from typing import TYPE_CHECKING, Any, TypedDict, TypeVar

import OpenSSL._util as pyOpenSSLutil
import OpenSSL.SSL
import OpenSSL.version
from twisted.internet.ssl import CertificateOptions, TLSVersion

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._deps_compat import (
    PYOPENSSL_X509_DEPRECATED,
    TWISTED_TLS_LIMITS_OFFBY1,
)
from scrapy.utils.python import to_unicode

if TYPE_CHECKING:
    from collections.abc import Callable

    from OpenSSL.crypto import X509Name

    from scrapy.settings import BaseSettings

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


# common


def _get_tls_version_limit(
    settings: BaseSettings, setting_name: str, converter: Callable[[str], _T]
) -> _T | None:
    setting: str | None = settings[setting_name]
    if setting is None:
        return None
    try:
        return converter(setting)
    except Exception as ex:
        raise ValueError(f"Unknown {setting_name} value: {setting}") from ex


def _get_tls_version_limits(
    settings: BaseSettings, converter: Callable[[str], _T]
) -> tuple[_T | None, _T | None]:
    return (
        _get_tls_version_limit(settings, "DOWNLOAD_TLS_MIN_VERSION", converter),
        _get_tls_version_limit(settings, "DOWNLOAD_TLS_MAX_VERSION", converter),
    )


# stdlib ssl module utils

_STDLIB_VERSION_MAP: dict[str, ssl.TLSVersion] = {
    "TLSv1.0": ssl.TLSVersion.TLSv1,
    "TLSv1.1": ssl.TLSVersion.TLSv1_1,
    "TLSv1.2": ssl.TLSVersion.TLSv1_2,
    "TLSv1.3": ssl.TLSVersion.TLSv1_3,
}


def _make_ssl_context(settings: BaseSettings) -> ssl.SSLContext:
    """Create an :class:`ssl.SSLContext` instance according to the settings.

    It's intended to be used in an HTTPS download handler.
    """

    tls_min_ver, tls_max_ver = _get_tls_version_limits(
        settings, _STDLIB_VERSION_MAP.__getitem__
    )
    ciphers_setting: str | None = settings["DOWNLOADER_CLIENT_TLS_CIPHERS"]
    verify_setting = settings.getbool("DOWNLOAD_VERIFY_CERTIFICATES")

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if verify_setting:
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_default_certs()
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    if tls_min_ver is not None:
        ctx.minimum_version = tls_min_ver
    if tls_max_ver is not None:
        ctx.maximum_version = tls_max_ver
    if ciphers_setting:
        ctx.set_ciphers(ciphers_setting)
    return ctx


def _make_insecure_ssl_ctx() -> ssl.SSLContext:
    """Create an SSL context that doesn't verify certificates.

    Compared to :func:`~scrapy.utils.ssl._make_ssl_context` this is much more
    simple.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _log_sslobj_debug_info(sslobj: ssl.SSLObject) -> None:
    cipher = sslobj.cipher()
    logger.debug(
        f"SSL connection to {sslobj.server_hostname}"
        f" using protocol {sslobj.version()},"
        f" cipher {cipher[0] if cipher else None}"
    )
    if cert := sslobj.getpeercert():
        # Not available without certificate verification
        logger.debug(
            f'SSL connection certificate: issuer "{cert["issuer"]}", subject "{cert["subject"]}"'
        )


# pyOpenSSL utils


def _ffi_buf_to_string(buf: Any) -> str:
    return to_unicode(pyOpenSSLutil.ffi.string(buf))


def ffi_buf_to_string(buf: Any) -> str:  # pragma: no cover
    warnings.warn(
        "ffi_buf_to_string() is deprecated.",
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    return ffi_buf_to_string(buf)


def _x509name_to_string(x509name: X509Name) -> str:
    # from OpenSSL.crypto.X509Name.__repr__
    # only used on pyOpenSSL < 24.3.0
    result_buffer: Any = pyOpenSSLutil.ffi.new("char[]", 512)
    pyOpenSSLutil.lib.X509_NAME_oneline(
        x509name._name, result_buffer, len(result_buffer)
    )
    return _ffi_buf_to_string(result_buffer)


def x509name_to_string(x509name: X509Name) -> str:  # pragma: no cover
    warnings.warn(
        "x509name_to_string() is deprecated.",
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    return _x509name_to_string(x509name)


def _get_temp_key_info(ssl_object: Any) -> str | None:
    # adapted from OpenSSL apps/s_cb.c::ssl_print_tmp_key()
    if not hasattr(pyOpenSSLutil.lib, "SSL_get_server_tmp_key"):
        # removed in cryptography 40.0.0 (required starting from pyOpenSSL 23.1.0)
        return None
    temp_key_p = pyOpenSSLutil.ffi.new("EVP_PKEY **")
    if not pyOpenSSLutil.lib.SSL_get_server_tmp_key(ssl_object, temp_key_p):
        return None
    temp_key = temp_key_p[0]
    if temp_key == pyOpenSSLutil.ffi.NULL:
        return None
    temp_key = pyOpenSSLutil.ffi.gc(temp_key, pyOpenSSLutil.lib.EVP_PKEY_free)
    key_info = []
    key_type = pyOpenSSLutil.lib.EVP_PKEY_id(temp_key)
    if key_type == pyOpenSSLutil.lib.EVP_PKEY_RSA:
        key_info.append("RSA")
    elif key_type == pyOpenSSLutil.lib.EVP_PKEY_DH:
        key_info.append("DH")
    elif key_type == pyOpenSSLutil.lib.EVP_PKEY_EC:
        key_info.append("ECDH")
        ec_key = pyOpenSSLutil.lib.EVP_PKEY_get1_EC_KEY(temp_key)
        ec_key = pyOpenSSLutil.ffi.gc(ec_key, pyOpenSSLutil.lib.EC_KEY_free)
        nid = pyOpenSSLutil.lib.EC_GROUP_get_curve_name(
            pyOpenSSLutil.lib.EC_KEY_get0_group(ec_key)
        )
        cname = pyOpenSSLutil.lib.EC_curve_nid2nist(nid)
        if cname == pyOpenSSLutil.ffi.NULL:
            cname = pyOpenSSLutil.lib.OBJ_nid2sn(nid)
        key_info.append(_ffi_buf_to_string(cname))
    else:
        key_info.append(_ffi_buf_to_string(pyOpenSSLutil.lib.OBJ_nid2sn(key_type)))
    key_info.append(f"{pyOpenSSLutil.lib.EVP_PKEY_bits(temp_key)} bits")
    return ", ".join(key_info)


def get_temp_key_info(ssl_object: Any) -> str | None:  # pragma: no cover
    warnings.warn(
        "get_temp_key_info() is deprecated. It's also a no-op with cryptography 40.0.0+.",
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    return _get_temp_key_info(ssl_object)


def get_openssl_version() -> str:
    system_openssl_bytes = OpenSSL.SSL.SSLeay_version(OpenSSL.SSL.SSLEAY_VERSION)
    system_openssl = system_openssl_bytes.decode("ascii", errors="replace")
    return f"{OpenSSL.version.__version__} ({system_openssl})"


def _log_ssl_conn_debug_info(hostname: str, connection: OpenSSL.SSL.Connection) -> None:
    logger.debug(
        "SSL connection to %s using protocol %s, cipher %s",
        hostname,
        connection.get_protocol_version_name(),
        connection.get_cipher_name(),
    )
    if PYOPENSSL_X509_DEPRECATED:
        if server_cert := connection.get_peer_certificate(as_cryptography=True):
            logger.debug(
                'SSL connection certificate: issuer "%s", subject "%s"',
                server_cert.issuer.rfc4514_string(),
                server_cert.subject.rfc4514_string(),
            )
    else:  # noqa: PLR5501
        if server_cert_pyopenssl := connection.get_peer_certificate():
            logger.debug(
                'SSL connection certificate: issuer "%s", subject "%s"',
                _x509name_to_string(server_cert_pyopenssl.get_issuer()),
                _x509name_to_string(server_cert_pyopenssl.get_subject()),
            )
    key_info = _get_temp_key_info(connection._ssl)
    if key_info:
        logger.debug("SSL temp key: %s", key_info)


# Twisted-specific


class _CertificateOptionsVersionKwargs(TypedDict, total=False):
    lowerMaximumSecurityTo: TLSVersion
    insecurelyLowerMinimumTo: TLSVersion
    raiseMinimumTo: TLSVersion


def _get_cert_options_version_kwargs(
    min_version: TLSVersion | None, max_version: TLSVersion | None
) -> _CertificateOptionsVersionKwargs:
    """Get TLS version kwargs for
    :class:`~twisted.internet.ssl.CertificateOptions` for the given limits."""
    result: _CertificateOptionsVersionKwargs = {}
    if max_version:
        if TWISTED_TLS_LIMITS_OFFBY1:
            # lowerMaximumSecurityTo is treated as 1 version lower than the passed one
            versions = list(TLSVersion.iterconstants())
            max_index = versions.index(max_version)
            if max_index + 1 >= len(versions):
                raise ValueError(
                    f"Due to an error in Twisted < 26.4.0 cannot set the maximum TLS version to {max_version.name}"
                )
            max_version = versions[max_index + 1]
        result["lowerMaximumSecurityTo"] = max_version
    if min_version:
        # We cannot pass both insecurelyLowerMinimumTo and raiseMinimumTo,
        # so we need to know the direction.

        # 1.0 in Twisted 22.8.0 and older, 1.2 in Twisted 22.10.0 and newer
        default_min = CertificateOptions._defaultMinimumTLSVersion
        if min_version < default_min:
            result["insecurelyLowerMinimumTo"] = min_version
        elif min_version > default_min:
            result["raiseMinimumTo"] = min_version
    return result

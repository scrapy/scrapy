from __future__ import annotations

from typing import TYPE_CHECKING, Any

import OpenSSL._util as pyOpenSSLutil
import OpenSSL.SSL
import OpenSSL.version

from scrapy.utils.python import to_unicode

if TYPE_CHECKING:
    from OpenSSL.crypto import X509Name


def ffi_buf_to_string(buf: Any) -> str:
    return to_unicode(pyOpenSSLutil.ffi.string(buf))


def x509name_to_string(x509name: X509Name) -> str:
    # from OpenSSL.crypto.X509Name.__repr__
    result_buffer: Any = pyOpenSSLutil.ffi.new("char[]", 512)
    pyOpenSSLutil.lib.X509_NAME_oneline(
        x509name._name, result_buffer, len(result_buffer)
    )

    return ffi_buf_to_string(result_buffer)


def get_temp_key_info(ssl_object: Any) -> str | None:
    # adapted from OpenSSL apps/s_cb.c::ssl_print_tmp_key()
    if not hasattr(pyOpenSSLutil.lib, "SSL_get_server_tmp_key"):
        # removed in cryptography 40.0.0
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
        key_info.append(ffi_buf_to_string(cname))
    else:
        key_info.append(ffi_buf_to_string(pyOpenSSLutil.lib.OBJ_nid2sn(key_type)))
    key_info.append(f"{pyOpenSSLutil.lib.EVP_PKEY_bits(temp_key)} bits")
    return ", ".join(key_info)


def get_openssl_version() -> str:
    system_openssl_bytes = OpenSSL.SSL.SSLeay_version(OpenSSL.SSL.SSLEAY_VERSION)
    system_openssl = system_openssl_bytes.decode("ascii", errors="replace")
    return f"{OpenSSL.version.__version__} ({system_openssl})"

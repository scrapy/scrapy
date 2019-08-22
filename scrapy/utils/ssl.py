# -*- coding: utf-8 -*-

import OpenSSL
import OpenSSL._util as pyOpenSSLutil

from scrapy.utils.python import to_native_str


# The OpenSSL symbol is present since 1.1.1 but it's not currently supported in any version of pyOpenSSL.
# Using the binding directly, as this code does, requires cryptography 2.4.
SSL_OP_NO_TLSv1_3 = getattr(pyOpenSSLutil.lib, 'SSL_OP_NO_TLSv1_3', 0)


def ffi_buf_to_string(buf):
    return to_native_str(pyOpenSSLutil.ffi.string(buf))


def x509name_to_string(x509name):
    # from OpenSSL.crypto.X509Name.__repr__
    result_buffer = pyOpenSSLutil.ffi.new("char[]", 512)
    pyOpenSSLutil.lib.X509_NAME_oneline(x509name._name, result_buffer, len(result_buffer))

    return ffi_buf_to_string(result_buffer)


def get_temp_key_info(ssl_object):
    if not hasattr(pyOpenSSLutil.lib, 'SSL_get_server_tmp_key'):  # requires OpenSSL 1.0.2
        return None

    # adapted from OpenSSL apps/s_cb.c::ssl_print_tmp_key()
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
        key_info.append('RSA')
    elif key_type == pyOpenSSLutil.lib.EVP_PKEY_DH:
        key_info.append('DH')
    elif key_type == pyOpenSSLutil.lib.EVP_PKEY_EC:
        key_info.append('ECDH')
        ec_key = pyOpenSSLutil.lib.EVP_PKEY_get1_EC_KEY(temp_key)
        ec_key = pyOpenSSLutil.ffi.gc(ec_key, pyOpenSSLutil.lib.EC_KEY_free)
        nid = pyOpenSSLutil.lib.EC_GROUP_get_curve_name(pyOpenSSLutil.lib.EC_KEY_get0_group(ec_key))
        cname = pyOpenSSLutil.lib.EC_curve_nid2nist(nid)
        if cname == pyOpenSSLutil.ffi.NULL:
            cname = pyOpenSSLutil.lib.OBJ_nid2sn(nid)
        key_info.append(ffi_buf_to_string(cname))
    else:
        key_info.append(ffi_buf_to_string(pyOpenSSLutil.lib.OBJ_nid2sn(key_type)))
    key_info.append('%s bits' % pyOpenSSLutil.lib.EVP_PKEY_bits(temp_key))
    return ', '.join(key_info)


def get_openssl_version():
    system_openssl = OpenSSL.SSL.SSLeay_version(
        OpenSSL.SSL.SSLEAY_VERSION
    ).decode('ascii', errors='replace')
    return '{} ({})'.format(OpenSSL.version.__version__, system_openssl)

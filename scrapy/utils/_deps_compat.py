import sys

from OpenSSL import __version__ as PYOPENSSL_VERSION_STRING
from packaging.version import Version
from twisted import version as TWISTED_VERSION
from twisted.python.versions import Version as TxVersion
from w3lib import __version__ as W3LIB_VERSION_STRING

# improved urllib.robotparser, https://github.com/python/cpython/pull/149374
STDLIB_IMPROVED_ROBOTFILEPARSER = sys.version_info >= (3, 14, 5) or (
    (3, 13, 14) <= sys.version_info < (3, 14)
)

TWISTED_FAILURE_HAS_STACK = TWISTED_VERSION < TxVersion("twisted", 24, 10, 0)
# changes to private _sslverify code, https://github.com/twisted/twisted/pull/12506
TWISTED_TLS_NEW_IMPL = TWISTED_VERSION >= TxVersion("twisted", 26, 4, 0)
# lowerMaximumSecurityTo off-by-1, https://github.com/twisted/twisted/issues/10232
TWISTED_TLS_LIMITS_OFFBY1 = TWISTED_VERSION < TxVersion("twisted", 26, 4, 0)

PYOPENSSL_VERSION = Version(PYOPENSSL_VERSION_STRING)
# pyOpenSSL X.509 APIs are deprecated and cryptography-based ones are preferred
PYOPENSSL_X509_DEPRECATED = PYOPENSSL_VERSION >= Version("24.3.0")
# SSL.Context.set_cipher_list() creates a temporary connection, making the context immutable
PYOPENSSL_SET_CIPHER_LIST_TMP_CONN = PYOPENSSL_VERSION < Version("25.2.0")

W3LIB_VERSION = Version(W3LIB_VERSION_STRING)
# safe_url_string() strips the input, https://github.com/scrapy/w3lib/pull/207
W3LIB_STRIPS_URLS = W3LIB_VERSION >= Version("2.1.1")

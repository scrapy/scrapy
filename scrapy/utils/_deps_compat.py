from OpenSSL import __version__ as PYOPENSSL_VERSION_STRING
from packaging.version import Version
from twisted import version as TWISTED_VERSION
from twisted.python.versions import Version as TxVersion

TWISTED_FAILURE_HAS_STACK = TWISTED_VERSION < TxVersion("twisted", 24, 10, 0)
# changes to private _sslverify code, https://github.com/twisted/twisted/pull/12506
# TODO: change to >= with the new version when it's released
TWISTED_TLS_NEW_IMPL = TWISTED_VERSION > TxVersion("twisted", 25, 5, 0)

PYOPENSSL_VERSION = Version(PYOPENSSL_VERSION_STRING)
# SSL.Context.use_certificate wants an X509 object, SSL.Context.use_privatekey wants a PKey object
PYOPENSSL_WANTS_X509_PKEY = PYOPENSSL_VERSION < Version("24.3.0")

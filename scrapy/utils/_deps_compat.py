from OpenSSL import __version__ as PYOPENSSL_VERSION_STRING
from packaging.version import Version
from twisted import version as TWISTED_VERSION
from twisted.python.versions import Version as TxVersion

TWISTED_FAILURE_HAS_STACK = TWISTED_VERSION < TxVersion("twisted", 24, 10, 0)

PYOPENSSL_VERSION = Version(PYOPENSSL_VERSION_STRING)
# SSL.Context.use_certificate() wants an X509 object, SSL.Context.use_privatekey() wants a PKey object
PYOPENSSL_WANTS_X509_PKEY = PYOPENSSL_VERSION < Version("24.3.0")
# SSL.Context.set_cipher_list() creates a temporary connection, making the context immutable
PYOPENSSL_SET_CIPHER_LIST_TMP_CONN = PYOPENSSL_VERSION < Version("25.2.0")

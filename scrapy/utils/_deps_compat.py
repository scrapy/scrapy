from twisted import version as TWISTED_VERSION
from twisted.python.versions import Version as TxVersion

TWISTED_FAILURE_HAS_STACK = TWISTED_VERSION < TxVersion("twisted", 24, 10, 0)

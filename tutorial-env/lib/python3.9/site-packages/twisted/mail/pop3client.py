"""
Deprecated POP3 client protocol implementation.

Don't use this module directly.  Use twisted.mail.pop3 instead.
"""
import warnings
from typing import List

from twisted.mail._pop3client import ERR, OK, POP3Client

warnings.warn(
    "twisted.mail.pop3client was deprecated in Twisted 21.2.0. Use twisted.mail.pop3 instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Fake usage to please pyflakes as we don't to add them to __all__.
OK
ERR
POP3Client

__all__: List[str] = []

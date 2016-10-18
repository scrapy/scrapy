"""
Avoid depending on any particular Python 3 compatibility approach.
"""

import sys


PY3 = sys.version_info[0] == 3
if PY3:  # pragma: nocover
    maketrans = bytes.maketrans
    text_type = str
else:  # pragma: nocover
    import string
    maketrans = string.maketrans
    text_type = unicode  # noqa

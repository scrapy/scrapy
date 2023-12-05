"""
A facade for either :mod:`unittest.mock` or its `rolling backport`__, if it is
installed, with a preference for the latter as it may well have newer functionality
and bugfixes.

The facade also contains any bugfixes that are critical to the operation of
functionality provided by testfixtures.

__ https://mock.readthedocs.io
"""
import sys

try:
    from mock import *
    from mock.mock import _Call
    from mock.mock import call as mock_call
    from mock import version_info as backport_version
except ImportError:
    backport_version = None
    class MockCall:
        pass
    mock_call = MockCall()
    try:
        from unittest.mock import *
        from unittest.mock import _Call
    except ImportError:  # pragma: no cover
        pass


has_backport = backport_version is not None

if not (
        (has_backport and backport_version[:3] > (2, 0, 0)) or
        (sys.version_info < (3, 0, 0) and not has_backport) or
        (3, 6, 7) < sys.version_info[:3] < (3, 7, 0) or
        sys.version_info[:3] > (3, 7, 1)
):  # pragma: no cover
    raise ImportError('Please upgrade Python (you have {}) or Mock Backport (You have {})'.format(
        sys.version_info, backport_version
    ))
parent_name = '_mock_parent'

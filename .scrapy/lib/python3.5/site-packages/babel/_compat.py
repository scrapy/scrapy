import sys
import array

PY2 = sys.version_info[0] == 2

_identity = lambda x: x


if not PY2:
    text_type = str
    string_types = (str,)
    integer_types = (int, )
    unichr = chr

    text_to_native = lambda s, enc: s

    iterkeys = lambda d: iter(d.keys())
    itervalues = lambda d: iter(d.values())
    iteritems = lambda d: iter(d.items())

    from io import StringIO, BytesIO
    import pickle

    izip = zip
    imap = map
    range_type = range

    cmp = lambda a, b: (a > b) - (a < b)

    array_tobytes = array.array.tobytes

else:
    text_type = unicode
    string_types = (str, unicode)
    integer_types = (int, long)

    text_to_native = lambda s, enc: s.encode(enc)
    unichr = unichr

    iterkeys = lambda d: d.iterkeys()
    itervalues = lambda d: d.itervalues()
    iteritems = lambda d: d.iteritems()

    from cStringIO import StringIO as BytesIO
    from StringIO import StringIO
    import cPickle as pickle

    from itertools import imap
    from itertools import izip
    range_type = xrange

    cmp = cmp

    array_tobytes = array.array.tostring


number_types = integer_types + (float,)


#
# Use cdecimal when available
#
from decimal import (Decimal as _dec,
                     InvalidOperation as _invop,
                     ROUND_HALF_EVEN as _RHE)
try:
    from cdecimal import (Decimal as _cdec,
                          InvalidOperation as _cinvop,
                          ROUND_HALF_EVEN as _CRHE)
    Decimal = _cdec
    InvalidOperation = (_invop, _cinvop)
    ROUND_HALF_EVEN = _CRHE
except ImportError:
    Decimal = _dec
    InvalidOperation = _invop
    ROUND_HALF_EVEN = _RHE

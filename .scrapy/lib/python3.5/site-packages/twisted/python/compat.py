# -*- test-case-name: twisted.test.test_compat -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Compatibility module to provide backwards compatibility for useful Python
features.

This is mainly for use of internal Twisted code. We encourage you to use
the latest version of Python directly from your code, if possible.

@var unicode: The type of Unicode strings, C{unicode} on Python 2 and C{str}
    on Python 3.

@var NativeStringIO: An in-memory file-like object that operates on the native
    string type (bytes in Python 2, unicode in Python 3).

@var urllib_parse: a URL-parsing module (urlparse on Python 2, urllib.parse on
    Python 3)
"""

from __future__ import absolute_import, division

import inspect
import os
import platform
import socket
import string
import struct
import sys
from types import MethodType as _MethodType

from io import TextIOBase, IOBase


if sys.version_info < (3, 0):
    _PY3 = False
else:
    _PY3 = True

if platform.python_implementation() == 'PyPy':
    _PYPY = True
else:
    _PYPY = False

def _shouldEnableNewStyle():
    """
    Returns whether or not we should enable the new-style conversion of
    old-style classes. It inspects the environment for C{TWISTED_NEWSTYLE},
    accepting an empty string, C{no}, C{false}, C{False}, and C{0} as falsey
    values and everything else as a truthy value.

    @rtype: L{bool}
    """
    value = os.environ.get('TWISTED_NEWSTYLE', '')

    if value in ['', 'no', 'false', 'False', '0']:
        return False
    else:
        return True


_EXPECT_NEWSTYLE = _PY3 or _shouldEnableNewStyle()


def currentframe(n=0):
    """
    In Python 3, L{inspect.currentframe} does not take a stack-level argument.
    Restore that functionality from Python 2 so we don't have to re-implement
    the C{f_back}-walking loop in places where it's called.

    @param n: The number of stack levels above the caller to walk.
    @type n: L{int}

    @return: a frame, n levels up the stack from the caller.
    @rtype: L{types.FrameType}
    """
    f = inspect.currentframe()
    for x in range(n + 1):
        f = f.f_back
    return f



def inet_pton(af, addr):
    if af == socket.AF_INET:
        return socket.inet_aton(addr)
    elif af == getattr(socket, 'AF_INET6', 'AF_INET6'):
        if [x for x in addr if x not in string.hexdigits + ':.']:
            raise ValueError("Illegal characters: %r" % (''.join(x),))

        parts = addr.split(':')
        elided = parts.count('')
        ipv4Component = '.' in parts[-1]

        if len(parts) > (8 - ipv4Component) or elided > 3:
            raise ValueError("Syntactically invalid address")

        if elided == 3:
            return '\x00' * 16

        if elided:
            zeros = ['0'] * (8 - len(parts) - ipv4Component + elided)

            if addr.startswith('::'):
                parts[:2] = zeros
            elif addr.endswith('::'):
                parts[-2:] = zeros
            else:
                idx = parts.index('')
                parts[idx:idx+1] = zeros

            if len(parts) != 8 - ipv4Component:
                raise ValueError("Syntactically invalid address")
        else:
            if len(parts) != (8 - ipv4Component):
                raise ValueError("Syntactically invalid address")

        if ipv4Component:
            if parts[-1].count('.') != 3:
                raise ValueError("Syntactically invalid address")
            rawipv4 = socket.inet_aton(parts[-1])
            unpackedipv4 = struct.unpack('!HH', rawipv4)
            parts[-1:] = [hex(x)[2:] for x in unpackedipv4]

        parts = [int(x, 16) for x in parts]
        return struct.pack('!8H', *parts)
    else:
        raise socket.error(97, 'Address family not supported by protocol')

def inet_ntop(af, addr):
    if af == socket.AF_INET:
        return socket.inet_ntoa(addr)
    elif af == socket.AF_INET6:
        if len(addr) != 16:
            raise ValueError("address length incorrect")
        parts = struct.unpack('!8H', addr)
        curBase = bestBase = None
        for i in range(8):
            if not parts[i]:
                if curBase is None:
                    curBase = i
                    curLen = 0
                curLen += 1
            else:
                if curBase is not None:
                    bestLen = None
                    if bestBase is None or curLen > bestLen:
                        bestBase = curBase
                        bestLen = curLen
                    curBase = None
        if curBase is not None and (bestBase is None or curLen > bestLen):
            bestBase = curBase
            bestLen = curLen
        parts = [hex(x)[2:] for x in parts]
        if bestBase is not None:
            parts[bestBase:bestBase + bestLen] = ['']
        if parts[0] == '':
            parts.insert(0, '')
        if parts[-1] == '':
            parts.insert(len(parts) - 1, '')
        return ':'.join(parts)
    else:
        raise socket.error(97, 'Address family not supported by protocol')

try:
    socket.AF_INET6
except AttributeError:
    socket.AF_INET6 = 'AF_INET6'

try:
    socket.inet_pton(socket.AF_INET6, "::")
except (AttributeError, NameError, socket.error):
    socket.inet_pton = inet_pton
    socket.inet_ntop = inet_ntop


adict = dict



if _PY3:
    # These are actually useless in Python 2 as well, but we need to go
    # through deprecation process there (ticket #5895):
    del adict, inet_pton, inet_ntop


set = set
frozenset = frozenset


try:
    from functools import reduce
except ImportError:
    reduce = reduce



def execfile(filename, globals, locals=None):
    """
    Execute a Python script in the given namespaces.

    Similar to the execfile builtin, but a namespace is mandatory, partly
    because that's a sensible thing to require, and because otherwise we'd
    have to do some frame hacking.

    This is a compatibility implementation for Python 3 porting, to avoid the
    use of the deprecated builtin C{execfile} function.
    """
    if locals is None:
        locals = globals
    with open(filename, "rbU") as fin:
        source = fin.read()
    code = compile(source, filename, "exec")
    exec(code, globals, locals)


try:
    cmp = cmp
except NameError:
    def cmp(a, b):
        """
        Compare two objects.

        Returns a negative number if C{a < b}, zero if they are equal, and a
        positive number if C{a > b}.
        """
        if a < b:
            return -1
        elif a == b:
            return 0
        else:
            return 1



def comparable(klass):
    """
    Class decorator that ensures support for the special C{__cmp__} method.

    On Python 2 this does nothing.

    On Python 3, C{__eq__}, C{__lt__}, etc. methods are added to the class,
    relying on C{__cmp__} to implement their comparisons.
    """
    # On Python 2, __cmp__ will just work, so no need to add extra methods:
    if not _PY3:
        return klass

    def __eq__(self, other):
        c = self.__cmp__(other)
        if c is NotImplemented:
            return c
        return c == 0


    def __ne__(self, other):
        c = self.__cmp__(other)
        if c is NotImplemented:
            return c
        return c != 0


    def __lt__(self, other):
        c = self.__cmp__(other)
        if c is NotImplemented:
            return c
        return c < 0


    def __le__(self, other):
        c = self.__cmp__(other)
        if c is NotImplemented:
            return c
        return c <= 0


    def __gt__(self, other):
        c = self.__cmp__(other)
        if c is NotImplemented:
            return c
        return c > 0


    def __ge__(self, other):
        c = self.__cmp__(other)
        if c is NotImplemented:
            return c
        return c >= 0

    klass.__lt__ = __lt__
    klass.__gt__ = __gt__
    klass.__le__ = __le__
    klass.__ge__ = __ge__
    klass.__eq__ = __eq__
    klass.__ne__ = __ne__
    return klass



if _PY3:
    unicode = str
    long = int
else:
    unicode = unicode
    long = long



def ioType(fileIshObject, default=unicode):
    """
    Determine the type which will be returned from the given file object's
    read() and accepted by its write() method as an argument.

    In other words, determine whether the given file is 'opened in text mode'.

    @param fileIshObject: Any object, but ideally one which resembles a file.
    @type fileIshObject: L{object}

    @param default: A default value to return when the type of C{fileIshObject}
        cannot be determined.
    @type default: L{type}

    @return: There are 3 possible return values:

            1. L{unicode}, if the file is unambiguously opened in text mode.

            2. L{bytes}, if the file is unambiguously opened in binary mode.

            3. L{basestring}, if we are on python 2 (the L{basestring} type
               does not exist on python 3) and the file is opened in binary
               mode, but has an encoding and can therefore accept both bytes
               and text reliably for writing, but will return L{bytes} from
               read methods.

            4. The C{default} parameter, if the given type is not understood.

    @rtype: L{type}
    """
    if isinstance(fileIshObject, TextIOBase):
        # If it's for text I/O, then it's for text I/O.
        return unicode
    if isinstance(fileIshObject, IOBase):
        # If it's for I/O but it's _not_ for text I/O, it's for bytes I/O.
        return bytes
    encoding = getattr(fileIshObject, 'encoding', None)
    import codecs
    if isinstance(fileIshObject, (codecs.StreamReader, codecs.StreamWriter)):
        # On StreamReaderWriter, the 'encoding' attribute has special meaning;
        # it is unambiguously unicode.
        if encoding:
            return unicode
        else:
            return bytes
    if not _PY3:
        # Special case: if we have an encoding file, we can *give* it unicode,
        # but we can't expect to *get* unicode.
        if isinstance(fileIshObject, file):
            if encoding is not None:
                return basestring
            else:
                return bytes
        from cStringIO import InputType, OutputType
        from StringIO import StringIO
        if isinstance(fileIshObject, (StringIO, InputType, OutputType)):
            return bytes
    return default



def nativeString(s):
    """
    Convert C{bytes} or C{unicode} to the native C{str} type, using ASCII
    encoding if conversion is necessary.

    @raise UnicodeError: The input string is not ASCII encodable/decodable.
    @raise TypeError: The input is neither C{bytes} nor C{unicode}.
    """
    if not isinstance(s, (bytes, unicode)):
        raise TypeError("%r is neither bytes nor unicode" % s)
    if _PY3:
        if isinstance(s, bytes):
            return s.decode("ascii")
        else:
            # Ensure we're limited to ASCII subset:
            s.encode("ascii")
    else:
        if isinstance(s, unicode):
            return s.encode("ascii")
        else:
            # Ensure we're limited to ASCII subset:
            s.decode("ascii")
    return s



def _matchingString(constantString, inputString):
    """
    Some functions, such as C{os.path.join}, operate on string arguments which
    may be bytes or text, and wish to return a value of the same type.  In
    those cases you may wish to have a string constant (in the case of
    C{os.path.join}, that constant would be C{os.path.sep}) involved in the
    parsing or processing, that must be of a matching type in order to use
    string operations on it.  L{_matchingString} will take a constant string
    (either L{bytes} or L{unicode}) and convert it to the same type as the
    input string.  C{constantString} should contain only characters from ASCII;
    to ensure this, it will be encoded or decoded regardless.

    @param constantString: A string literal used in processing.
    @type constantString: L{unicode} or L{bytes}

    @param inputString: A byte string or text string provided by the user.
    @type inputString: L{unicode} or L{bytes}

    @return: C{constantString} converted into the same type as C{inputString}
    @rtype: the type of C{inputString}
    """
    if isinstance(constantString, bytes):
        otherType = constantString.decode("ascii")
    else:
        otherType = constantString.encode("ascii")
    if type(constantString) == type(inputString):
        return constantString
    else:
        return otherType



if _PY3:
    def reraise(exception, traceback):
        raise exception.with_traceback(traceback)
else:
    exec("""def reraise(exception, traceback):
        raise exception.__class__, exception, traceback""")

reraise.__doc__ = """
Re-raise an exception, with an optional traceback, in a way that is compatible
with both Python 2 and Python 3.

Note that on Python 3, re-raised exceptions will be mutated, with their
C{__traceback__} attribute being set.

@param exception: The exception instance.
@param traceback: The traceback to use, or L{None} indicating a new traceback.
"""



if _PY3:
    from io import StringIO as NativeStringIO
else:
    from io import BytesIO as NativeStringIO



# Functions for dealing with Python 3's bytes type, which is somewhat
# different than Python 2's:
if _PY3:
    def iterbytes(originalBytes):
        for i in range(len(originalBytes)):
            yield originalBytes[i:i+1]


    def intToBytes(i):
        return ("%d" % i).encode("ascii")


    # Ideally we would use memoryview, but it has a number of differences from
    # the Python 2 buffer() that make that impractical
    # (http://bugs.python.org/issue15945, incompatibility with pyOpenSSL due to
    # PyArg_ParseTuple differences.)
    def lazyByteSlice(object, offset=0, size=None):
        """
        Return a copy of the given bytes-like object.

        If an offset is given, the copy starts at that offset. If a size is
        given, the copy will only be of that length.

        @param object: C{bytes} to be copied.

        @param offset: C{int}, starting index of copy.

        @param size: Optional, if an C{int} is given limit the length of copy
            to this size.
        """
        if size is None:
            return object[offset:]
        else:
            return object[offset:(offset + size)]


    def networkString(s):
        if not isinstance(s, unicode):
            raise TypeError("Can only convert text to bytes on Python 3")
        return s.encode('ascii')
else:
    def iterbytes(originalBytes):
        return originalBytes


    def intToBytes(i):
        return b"%d" % i


    lazyByteSlice = buffer

    def networkString(s):
        if not isinstance(s, str):
            raise TypeError("Can only pass-through bytes on Python 2")
        # Ensure we're limited to ASCII subset:
        s.decode('ascii')
        return s

iterbytes.__doc__ = """
Return an iterable wrapper for a C{bytes} object that provides the behavior of
iterating over C{bytes} on Python 2.

In particular, the results of iteration are the individual bytes (rather than
integers as on Python 3).

@param originalBytes: A C{bytes} object that will be wrapped.
"""

intToBytes.__doc__ = """
Convert the given integer into C{bytes}, as ASCII-encoded Arab numeral.

In other words, this is equivalent to calling C{bytes} in Python 2 on an
integer.

@param i: The C{int} to convert to C{bytes}.
@rtype: C{bytes}
"""

networkString.__doc__ = """
Convert the native string type to C{bytes} if it is not already C{bytes} using
ASCII encoding if conversion is necessary.

This is useful for sending text-like bytes that are constructed using string
interpolation.  For example, this is safe on Python 2 and Python 3:

    networkString("Hello %d" % (n,))

@param s: A native string to convert to bytes if necessary.
@type s: C{str}

@raise UnicodeError: The input string is not ASCII encodable/decodable.
@raise TypeError: The input is neither C{bytes} nor C{unicode}.

@rtype: C{bytes}
"""


try:
    StringType = basestring
except NameError:
    # Python 3+
    StringType = str

try:
    from types import InstanceType
except ImportError:
    # Python 3+
    InstanceType = object

try:
    from types import FileType
except ImportError:
    # Python 3+
    FileType = IOBase

if _PY3:
    import urllib.parse as urllib_parse
    from html import escape
    from urllib.parse import quote as urlquote
    from urllib.parse import unquote as urlunquote
    from http import cookiejar as cookielib
else:
    import urlparse as urllib_parse
    from cgi import escape
    from urllib import quote as urlquote
    from urllib import unquote as urlunquote
    import cookielib


# Dealing with the differences in items/iteritems
if _PY3:
    def iteritems(d):
        return d.items()

    def itervalues(d):
        return d.values()

    def items(d):
        return list(d.items())

    xrange = range
    izip = zip
else:
    def iteritems(d):
        return d.iteritems()

    def itervalues(d):
        return d.itervalues()

    def items(d):
        return d.items()

    xrange = xrange
    from itertools import izip
    izip # shh pyflakes


iteritems.__doc__ = """
Return an iterable of the items of C{d}.

@type d: L{dict}
@rtype: iterable
"""

itervalues.__doc__ = """
Return an iterable of the values of C{d}.

@type d: L{dict}
@rtype: iterable
"""

items.__doc__ = """
Return a list of the items of C{d}.

@type d: L{dict}
@rtype: L{list}
"""

def _keys(d):
    """
    Return a list of the keys of C{d}.

    @type d: L{dict}
    @rtype: L{list}
    """
    if _PY3:
        return list(d.keys())
    else:
        return d.keys()



def bytesEnviron():
    """
    Return a L{dict} of L{os.environ} where all text-strings are encoded into
    L{bytes}.
    """
    if not _PY3:
        # On py2, nothing to do.
        return dict(os.environ)

    target = dict()
    for x, y in os.environ.items():
        target[os.environ.encodekey(x)] = os.environ.encodevalue(y)

    return target



def _constructMethod(cls, name, self):
    """
    Construct a bound method.

    @param cls: The class that the method should be bound to.
    @type cls: L{types.ClassType} or L{type}.

    @param name: The name of the method.
    @type name: native L{str}

    @param self: The object that the method is bound to.
    @type self: any object

    @return: a bound method
    @rtype: L{types.MethodType}
    """
    func = cls.__dict__[name]
    if _PY3:
        return _MethodType(func, self)
    return _MethodType(func, self, cls)



from twisted.python.versions import Version
from twisted.python.deprecate import deprecatedModuleAttribute

from collections import OrderedDict

deprecatedModuleAttribute(
    Version("Twisted", 15, 5, 0),
    "Use collections.OrderedDict instead.",
    "twisted.python.compat",
    "OrderedDict")

if _PY3:
    from base64 import encodebytes as _b64encodebytes
    from base64 import decodebytes as _b64decodebytes
else:
    from base64 import encodestring as _b64encodebytes
    from base64 import decodestring as _b64decodebytes



def _bytesChr(i):
    """
    Like L{chr} but always works on ASCII, returning L{bytes}.

    @param i: The ASCII code point to return.
    @type i: L{int}

    @rtype: L{bytes}
    """
    if _PY3:
        return bytes([i])
    else:
        return chr(i)



try:
    from sys import intern
except ImportError:
    intern = intern



def _coercedUnicode(s):
    """
    Coerce ASCII-only byte strings into unicode for Python 2.

    In Python 2 C{unicode(b'bytes')} returns a unicode string C{'bytes'}. In
    Python 3, the equivalent C{str(b'bytes')} will return C{"b'bytes'"}
    instead. This function mimics the behavior for Python 2. It will decode the
    byte string as ASCII. In Python 3 it simply raises a L{TypeError} when
    passing a byte string. Unicode strings are returned as-is.

    @param s: The string to coerce.
    @type s: L{bytes} or L{unicode}

    @raise UnicodeError: The input L{bytes} is not ASCII decodable.
    @raise TypeError: The input is L{bytes} on Python 3.
    """
    if isinstance(s, bytes):
        if _PY3:
            raise TypeError("Expected str not %r (bytes)" % (s,))
        else:
            return s.decode('ascii')
    else:
        return s



if _PY3:
    unichr = chr
    raw_input = input
else:
    unichr = unichr
    raw_input = raw_input



def _bytesRepr(bytestring):
    """
    Provide a repr for a byte string that begins with 'b' on both
    Python 2 and 3.

    @param bytestring: The string to repr.
    @type bytestring: L{bytes}

    @raise TypeError: The input is not L{bytes}.

    @return: The repr with a leading 'b'.
    @rtype: L{bytes}
    """
    if not isinstance(bytestring, bytes):
        raise TypeError("Expected bytes not %r" % (bytestring,))

    if _PY3:
        return repr(bytestring)
    else:
        return 'b' + repr(bytestring)



__all__ = [
    "reraise",
    "execfile",
    "frozenset",
    "reduce",
    "set",
    "cmp",
    "comparable",
    "OrderedDict",
    "nativeString",
    "NativeStringIO",
    "networkString",
    "unicode",
    "iterbytes",
    "intToBytes",
    "lazyByteSlice",
    "StringType",
    "InstanceType",
    "FileType",
    "items",
    "iteritems",
    "itervalues",
    "xrange",
    "urllib_parse",
    "bytesEnviron",
    "escape",
    "urlquote",
    "urlunquote",
    "cookielib",
    "_keys",
    "_b64encodebytes",
    "_b64decodebytes",
    "_bytesChr",
    "_coercedUnicode",
    "_bytesRepr",
    "intern",
    "unichr",
    "raw_input",
]

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


import inspect
import os
import platform
import socket
import sys
import urllib.parse as urllib_parse
import warnings
from collections.abc import Sequence
from functools import reduce
from html import escape
from http import cookiejar as cookielib
from io import IOBase, StringIO as NativeStringIO, TextIOBase
from sys import intern
from types import FrameType, MethodType as _MethodType
from typing import Any, AnyStr, cast
from urllib.parse import quote as urlquote, unquote as urlunquote

from incremental import Version

from twisted.python.deprecate import deprecated, deprecatedModuleAttribute

if sys.version_info >= (3, 7, 0):
    _PY37PLUS = True
else:
    _PY37PLUS = False

if platform.python_implementation() == "PyPy":
    _PYPY = True
else:
    _PYPY = False

FileType = IOBase
deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Obsolete alias for io.IOBase",
    __name__,
    "FileType",
)

frozenset = frozenset
deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Obsolete alias for frozenset builtin type",
    __name__,
    "frozenset",
)

InstanceType = object
deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Old-style classes don't exist in Python 3",
    __name__,
    "InstanceType",
)

izip = zip
deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Obsolete alias for zip() builtin",
    __name__,
    "izip",
)

long = int
deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Obsolete alias for int builtin type",
    __name__,
    "long",
)

range = range
deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Obsolete alias for range() builtin",
    __name__,
    "range",
)

raw_input = input
deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Obsolete alias for input() builtin",
    __name__,
    "raw_input",
)

set = set
deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Obsolete alias for set builtin type",
    __name__,
    "set",
)

StringType = str
deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Obsolete alias for str builtin type",
    __name__,
    "StringType",
)

unichr = chr
deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Obsolete alias for chr() builtin",
    __name__,
    "unichr",
)

unicode = str
deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Obsolete alias for str builtin type",
    __name__,
    "unicode",
)

xrange = range
deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Obsolete alias for range() builtin",
    __name__,
    "xrange",
)


@deprecated(Version("Twisted", 21, 2, 0), replacement="d.items()")
def iteritems(d):
    """
    Return an iterable of the items of C{d}.

    @type d: L{dict}
    @rtype: iterable
    """
    return d.items()


@deprecated(Version("Twisted", 21, 2, 0), replacement="d.values()")
def itervalues(d):
    """
    Return an iterable of the values of C{d}.

    @type d: L{dict}
    @rtype: iterable
    """
    return d.values()


@deprecated(Version("Twisted", 21, 2, 0), replacement="list(d.items())")
def items(d):
    """
    Return a list of the items of C{d}.

    @type d: L{dict}
    @rtype: L{list}
    """
    return list(d.items())


def currentframe(n: int = 0) -> FrameType:
    """
    In Python 3, L{inspect.currentframe} does not take a stack-level argument.
    Restore that functionality from Python 2 so we don't have to re-implement
    the C{f_back}-walking loop in places where it's called.

    @param n: The number of stack levels above the caller to walk.

    @return: a frame, n levels up the stack from the caller.
    """
    f = inspect.currentframe()
    for x in range(n + 1):
        assert f is not None
        f = f.f_back
    assert f is not None
    return f


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
    with open(filename, "rb") as fin:
        source = fin.read()
    code = compile(source, filename, "exec")
    exec(code, globals, locals)


# type note: Can't find a Comparable type, despite
# https://github.com/python/typing/issues/59
def cmp(a: object, b: object) -> int:
    """
    Compare two objects.

    Returns a negative number if C{a < b}, zero if they are equal, and a
    positive number if C{a > b}.
    """
    if a < b:  # type: ignore[operator]
        return -1
    elif a == b:
        return 0
    else:
        return 1


def comparable(klass):
    """
    Class decorator that ensures support for the special C{__cmp__} method.

    C{__eq__}, C{__lt__}, etc. methods are added to the class, relying on
    C{__cmp__} to implement their comparisons.
    """

    def __eq__(self: Any, other: object) -> bool:
        c = cast(bool, self.__cmp__(other))
        if c is NotImplemented:
            return c
        return c == 0

    def __ne__(self: Any, other: object) -> bool:
        c = cast(bool, self.__cmp__(other))
        if c is NotImplemented:
            return c
        return c != 0

    def __lt__(self: Any, other: object) -> bool:
        c = cast(bool, self.__cmp__(other))
        if c is NotImplemented:
            return c
        return c < 0

    def __le__(self: Any, other: object) -> bool:
        c = cast(bool, self.__cmp__(other))
        if c is NotImplemented:
            return c
        return c <= 0

    def __gt__(self: Any, other: object) -> bool:
        c = cast(bool, self.__cmp__(other))
        if c is NotImplemented:
            return c
        return c > 0

    def __ge__(self: Any, other: object) -> bool:
        c = cast(bool, self.__cmp__(other))
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


def ioType(fileIshObject, default=str):
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

            1. L{str}, if the file is unambiguously opened in text mode.

            2. L{bytes}, if the file is unambiguously opened in binary mode.

            3. The C{default} parameter, if the given type is not understood.

    @rtype: L{type}
    """
    if isinstance(fileIshObject, TextIOBase):
        # If it's for text I/O, then it's for text I/O.
        return str
    if isinstance(fileIshObject, IOBase):
        # If it's for I/O but it's _not_ for text I/O, it's for bytes I/O.
        return bytes
    encoding = getattr(fileIshObject, "encoding", None)
    import codecs

    if isinstance(fileIshObject, (codecs.StreamReader, codecs.StreamWriter)):
        # On StreamReaderWriter, the 'encoding' attribute has special meaning;
        # it is unambiguously text.
        if encoding:
            return str
        else:
            return bytes
    return default


def nativeString(s: AnyStr) -> str:
    """
    Convert C{bytes} or C{str} to C{str} type, using ASCII encoding if
    conversion is necessary.

    @raise UnicodeError: The input string is not ASCII encodable/decodable.
    @raise TypeError: The input is neither C{bytes} nor C{str}.
    """
    if not isinstance(s, (bytes, str)):
        raise TypeError("%r is neither bytes nor str" % s)
    if isinstance(s, bytes):
        return s.decode("ascii")
    else:
        # Ensure we're limited to ASCII subset:
        s.encode("ascii")
    return s


def _matchingString(constantString, inputString):
    """
    Some functions, such as C{os.path.join}, operate on string arguments which
    may be bytes or text, and wish to return a value of the same type.  In
    those cases you may wish to have a string constant (in the case of
    C{os.path.join}, that constant would be C{os.path.sep}) involved in the
    parsing or processing, that must be of a matching type in order to use
    string operations on it.  L{_matchingString} will take a constant string
    (either L{bytes} or L{str}) and convert it to the same type as the
    input string.  C{constantString} should contain only characters from ASCII;
    to ensure this, it will be encoded or decoded regardless.

    @param constantString: A string literal used in processing.
    @type constantString: L{str} or L{bytes}

    @param inputString: A byte string or text string provided by the user.
    @type inputString: L{str} or L{bytes}

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


@deprecated(
    Version("Twisted", 21, 2, 0),
    replacement="raise exception.with_traceback(traceback)",
)
def reraise(exception, traceback):
    """
    Re-raise an exception, with an optional traceback.

    Re-raised exceptions will be mutated, with their C{__traceback__} attribute
    being set.

    @param exception: The exception instance.
    @param traceback: The traceback to use, or L{None} indicating a new
    traceback.
    """
    raise exception.with_traceback(traceback)


def iterbytes(originalBytes):
    """
    Return an iterable wrapper for a C{bytes} object that provides the behavior
    of iterating over C{bytes} on Python 2.

    In particular, the results of iteration are the individual bytes (rather
    than integers as on Python 3).

    @param originalBytes: A C{bytes} object that will be wrapped.
    """
    for i in range(len(originalBytes)):
        yield originalBytes[i : i + 1]


@deprecated(Version("Twisted", 21, 2, 0), replacement="b'%d'")
def intToBytes(i: int) -> bytes:
    """
    Convert the given integer into C{bytes}, as ASCII-encoded Arab numeral.

    @param i: The C{int} to convert to C{bytes}.
    @rtype: C{bytes}
    """
    return b"%d" % (i,)


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
    view = memoryview(object)
    if size is None:
        return view[offset:]
    else:
        return view[offset : (offset + size)]


def networkString(s: str) -> bytes:
    """
    Convert a string to L{bytes} using ASCII encoding.

    This is useful for sending text-like bytes that are constructed using
    string interpolation.  For example::

        networkString("Hello %d" % (n,))

    @param s: A string to convert to bytes.
    @type s: L{str}

    @raise UnicodeError: The input string is not ASCII encodable.
    @raise TypeError: The input is not L{str}.

    @rtype: L{bytes}
    """
    if not isinstance(s, str):
        raise TypeError("Can only convert strings to bytes")
    return s.encode("ascii")


@deprecated(Version("Twisted", 21, 2, 0), replacement="os.environb")
def bytesEnviron():
    """
    Return a L{dict} of L{os.environ} where all text-strings are encoded into
    L{bytes}.

    This function is POSIX only; environment variables are always text strings
    on Windows.
    """
    encodekey = os.environ.encodekey
    encodevalue = os.environ.encodevalue

    return {encodekey(x): encodevalue(y) for x, y in os.environ.items()}  # type: ignore[call-arg]


def _constructMethod(cls, name, self):
    """
    Construct a bound method.

    @param cls: The class that the method should be bound to.
    @type cls: L{type}

    @param name: The name of the method.
    @type name: native L{str}

    @param self: The object that the method is bound to.
    @type self: any object

    @return: a bound method
    @rtype: L{_MethodType}
    """
    func = cls.__dict__[name]
    return _MethodType(func, self)


def _get_async_param(isAsync=None, **kwargs):
    """
    Provide a backwards-compatible way to get async param value that does not
    cause a syntax error under Python 3.7.

    @param isAsync: isAsync param value (should default to None)
    @type isAsync: L{bool}

    @param kwargs: keyword arguments of the caller (only async is allowed)
    @type kwargs: L{dict}

    @raise TypeError: Both isAsync and async specified.

    @return: Final isAsync param value
    @rtype: L{bool}
    """
    if "async" in kwargs:
        warnings.warn(
            "'async' keyword argument is deprecated, please use isAsync",
            DeprecationWarning,
            stacklevel=2,
        )
    if isAsync is None and "async" in kwargs:
        isAsync = kwargs.pop("async")
    if kwargs:
        raise TypeError
    return bool(isAsync)


def _pypy3BlockingHack():
    """
    Work around U{https://foss.heptapod.net/pypy/pypy/-/issues/3051}
    by replacing C{socket.fromfd} with a more conservative version.
    """
    try:
        from fcntl import F_GETFL, F_SETFL, fcntl
    except ImportError:
        return
    if not _PYPY:
        return

    def fromFDWithoutModifyingFlags(fd, family, type, proto=None):
        passproto = [proto] * (proto is not None)
        flags = fcntl(fd, F_GETFL)
        try:
            return realFromFD(fd, family, type, *passproto)
        finally:
            fcntl(fd, F_SETFL, flags)

    realFromFD = socket.fromfd
    if realFromFD.__name__ == fromFDWithoutModifyingFlags.__name__:
        return
    socket.fromfd = fromFDWithoutModifyingFlags


_pypy3BlockingHack()


deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Use functools.reduce() directly",
    __name__,
    "reduce",
)

deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Use io.StringIO directly",
    __name__,
    "NativeStringIO",
)

deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Import urllib.parse directly",
    __name__,
    "urllib_parse",
)

deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0), "Use html.escape directly", __name__, "escape"
)

deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Use urllib.parse.quote() directly",
    __name__,
    "urlquote",
)

deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Use urllib.parse.unquote() directly",
    __name__,
    "urlunquote",
)

deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Use http.cookiejar directly",
    __name__,
    "cookielib",
)

deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0), "Use sys.intern() directly", __name__, "intern"
)

deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Use collections.abc.Sequence directly",
    __name__,
    "Sequence",
)


__all__ = [
    "reraise",
    "execfile",
    "frozenset",
    "reduce",
    "set",
    "cmp",
    "comparable",
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
    "range",
    "xrange",
    "urllib_parse",
    "bytesEnviron",
    "escape",
    "urlquote",
    "urlunquote",
    "cookielib",
    "intern",
    "unichr",
    "raw_input",
    "_get_async_param",
    "Sequence",
]

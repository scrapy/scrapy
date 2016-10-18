# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Tests for L{twisted.python.compat}.
"""

from __future__ import division, absolute_import

import socket, sys, traceback, io, codecs

from twisted.trial import unittest

from twisted.python.compat import (
    reduce, execfile, _PY3, _PYPY, comparable, cmp, nativeString,
    networkString, unicode as unicodeCompat, lazyByteSlice, reraise,
    NativeStringIO, iterbytes, intToBytes, ioType, bytesEnviron, iteritems,
    _coercedUnicode, unichr, raw_input, _bytesRepr
)
from twisted.python.filepath import FilePath



class IOTypeTests(unittest.SynchronousTestCase):
    """
    Test cases for determining a file-like object's type.
    """

    def test_3StringIO(self):
        """
        An L{io.StringIO} accepts and returns text.
        """
        self.assertEqual(ioType(io.StringIO()), unicodeCompat)


    def test_3BytesIO(self):
        """
        An L{io.BytesIO} accepts and returns bytes.
        """
        self.assertEqual(ioType(io.BytesIO()), bytes)


    def test_3openTextMode(self):
        """
        A file opened via 'io.open' in text mode accepts and returns text.
        """
        with io.open(self.mktemp(), "w") as f:
            self.assertEqual(ioType(f), unicodeCompat)


    def test_3openBinaryMode(self):
        """
        A file opened via 'io.open' in binary mode accepts and returns bytes.
        """
        with io.open(self.mktemp(), "wb") as f:
            self.assertEqual(ioType(f), bytes)


    def test_2openTextMode(self):
        """
        The special built-in console file in Python 2 which has an 'encoding'
        attribute should qualify as a special type, since it accepts both bytes
        and text faithfully.
        """
        class VerySpecificLie(file):
            """
            In their infinite wisdom, the CPython developers saw fit not to
            allow us a writable 'encoding' attribute on the built-in 'file'
            type in Python 2, despite making it writable in C with
            PyFile_SetEncoding.

            Pretend they did not do that.
            """
            encoding = 'utf-8'

        self.assertEqual(ioType(VerySpecificLie(self.mktemp(), "wb")),
                          basestring)


    def test_2StringIO(self):
        """
        Python 2's L{StringIO} and L{cStringIO} modules are both binary I/O.
        """
        from cStringIO import StringIO as cStringIO
        from StringIO import StringIO
        self.assertEqual(ioType(StringIO()), bytes)
        self.assertEqual(ioType(cStringIO()), bytes)


    def test_2openBinaryMode(self):
        """
        The normal 'open' builtin in Python 2 will always result in bytes I/O.
        """
        with open(self.mktemp(), "w") as f:
            self.assertEqual(ioType(f), bytes)

    if _PY3:
        test_2openTextMode.skip = "The 'file' type is no longer available."
        test_2openBinaryMode.skip = "'io.open' is now the same as 'open'."
        test_2StringIO.skip = ("The 'StringIO' and 'cStringIO' modules were "
                               "subsumed by the 'io' module.")


    def test_codecsOpenBytes(self):
        """
        The L{codecs} module, oddly, returns a file-like object which returns
        bytes when not passed an 'encoding' argument.
        """
        with codecs.open(self.mktemp(), 'wb') as f:
            self.assertEqual(ioType(f), bytes)


    def test_codecsOpenText(self):
        """
        When passed an encoding, however, the L{codecs} module returns unicode.
        """
        with codecs.open(self.mktemp(), 'wb', encoding='utf-8') as f:
            self.assertEqual(ioType(f), unicodeCompat)


    def test_defaultToText(self):
        """
        When passed an object about which no sensible decision can be made, err
        on the side of unicode.
        """
        self.assertEqual(ioType(object()), unicodeCompat)



class CompatTests(unittest.SynchronousTestCase):
    """
    Various utility functions in C{twisted.python.compat} provide same
    functionality as modern Python variants.
    """

    def test_set(self):
        """
        L{set} should behave like the expected set interface.
        """
        a = set()
        a.add('b')
        a.add('c')
        a.add('a')
        b = list(a)
        b.sort()
        self.assertEqual(b, ['a', 'b', 'c'])
        a.remove('b')
        b = list(a)
        b.sort()
        self.assertEqual(b, ['a', 'c'])

        a.discard('d')

        b = set(['r', 's'])
        d = a.union(b)
        b = list(d)
        b.sort()
        self.assertEqual(b, ['a', 'c', 'r', 's'])


    def test_frozenset(self):
        """
        L{frozenset} should behave like the expected frozenset interface.
        """
        a = frozenset(['a', 'b'])
        self.assertRaises(AttributeError, getattr, a, "add")
        self.assertEqual(sorted(a), ['a', 'b'])

        b = frozenset(['r', 's'])
        d = a.union(b)
        b = list(d)
        b.sort()
        self.assertEqual(b, ['a', 'b', 'r', 's'])


    def test_reduce(self):
        """
        L{reduce} should behave like the builtin reduce.
        """
        self.assertEqual(15, reduce(lambda x, y: x + y, [1, 2, 3, 4, 5]))
        self.assertEqual(16, reduce(lambda x, y: x + y, [1, 2, 3, 4, 5], 1))



class IPv6Tests(unittest.SynchronousTestCase):
    """
    C{inet_pton} and C{inet_ntop} implementations support IPv6.
    """

    def testNToP(self):
        from twisted.python.compat import inet_ntop

        f = lambda a: inet_ntop(socket.AF_INET6, a)
        g = lambda a: inet_ntop(socket.AF_INET, a)

        self.assertEqual('::', f('\x00' * 16))
        self.assertEqual('::1', f('\x00' * 15 + '\x01'))
        self.assertEqual(
            'aef:b01:506:1001:ffff:9997:55:170',
            f('\x0a\xef\x0b\x01\x05\x06\x10\x01\xff\xff\x99\x97\x00\x55\x01'
              '\x70'))

        self.assertEqual('1.0.1.0', g('\x01\x00\x01\x00'))
        self.assertEqual('170.85.170.85', g('\xaa\x55\xaa\x55'))
        self.assertEqual('255.255.255.255', g('\xff\xff\xff\xff'))

        self.assertEqual('100::', f('\x01' + '\x00' * 15))
        self.assertEqual('100::1', f('\x01' + '\x00' * 14 + '\x01'))


    def testPToN(self):
        from twisted.python.compat import inet_pton

        f = lambda a: inet_pton(socket.AF_INET6, a)
        g = lambda a: inet_pton(socket.AF_INET, a)

        self.assertEqual('\x00\x00\x00\x00', g('0.0.0.0'))
        self.assertEqual('\xff\x00\xff\x00', g('255.0.255.0'))
        self.assertEqual('\xaa\xaa\xaa\xaa', g('170.170.170.170'))

        self.assertEqual('\x00' * 16, f('::'))
        self.assertEqual('\x00' * 16, f('0::0'))
        self.assertEqual('\x00\x01' + '\x00' * 14, f('1::'))
        self.assertEqual(
            '\x45\xef\x76\xcb\x00\x1a\x56\xef\xaf\xeb\x0b\xac\x19\x24\xae\xae',
            f('45ef:76cb:1a:56ef:afeb:bac:1924:aeae'))

        self.assertEqual('\x00' * 14 + '\x00\x01', f('::1'))
        self.assertEqual('\x00' * 12 + '\x01\x02\x03\x04', f('::1.2.3.4'))
        self.assertEqual(
            '\x00\x01\x00\x02\x00\x03\x00\x04\x00\x05\x00\x06\x01\x02\x03\xff',
            f('1:2:3:4:5:6:1.2.3.255'))

        for badaddr in ['1:2:3:4:5:6:7:8:', ':1:2:3:4:5:6:7:8', '1::2::3',
                        '1:::3', ':::', '1:2', '::1.2', '1.2.3.4::',
                        'abcd:1.2.3.4:abcd:abcd:abcd:abcd:abcd',
                        '1234:1.2.3.4:1234:1234:1234:1234:1234:1234',
                        '1.2.3.4']:
            self.assertRaises(ValueError, f, badaddr)

if _PY3:
    IPv6Tests.skip = "These tests are only relevant to old versions of Python"



class ExecfileCompatTests(unittest.SynchronousTestCase):
    """
    Tests for the Python 3-friendly L{execfile} implementation.
    """

    def writeScript(self, content):
        """
        Write L{content} to a new temporary file, returning the L{FilePath}
        for the new file.
        """
        path = self.mktemp()
        with open(path, "wb") as f:
            f.write(content.encode("ascii"))
        return FilePath(path.encode("utf-8"))


    def test_execfileGlobals(self):
        """
        L{execfile} executes the specified file in the given global namespace.
        """
        script = self.writeScript(u"foo += 1\n")
        globalNamespace = {"foo": 1}
        execfile(script.path, globalNamespace)
        self.assertEqual(2, globalNamespace["foo"])


    def test_execfileGlobalsAndLocals(self):
        """
        L{execfile} executes the specified file in the given global and local
        namespaces.
        """
        script = self.writeScript(u"foo += 1\n")
        globalNamespace = {"foo": 10}
        localNamespace = {"foo": 20}
        execfile(script.path, globalNamespace, localNamespace)
        self.assertEqual(10, globalNamespace["foo"])
        self.assertEqual(21, localNamespace["foo"])


    def test_execfileUniversalNewlines(self):
        """
        L{execfile} reads in the specified file using universal newlines so
        that scripts written on one platform will work on another.
        """
        for lineEnding in u"\n", u"\r", u"\r\n":
            script = self.writeScript(u"foo = 'okay'" + lineEnding)
            globalNamespace = {"foo": None}
            execfile(script.path, globalNamespace)
            self.assertEqual("okay", globalNamespace["foo"])



class PY3Tests(unittest.SynchronousTestCase):
    """
    Identification of Python 2 vs. Python 3.
    """

    def test_python2(self):
        """
        On Python 2, C{_PY3} is False.
        """
        if sys.version.startswith("2."):
            self.assertFalse(_PY3)


    def test_python3(self):
        """
        On Python 3, C{_PY3} is True.
        """
        if sys.version.startswith("3."):
            self.assertTrue(_PY3)



class PYPYTest(unittest.SynchronousTestCase):
    """
    Identification of PyPy.
    """

    def test_PYPY(self):
        """
        On PyPy, L{_PYPY} is True.
        """
        if 'PyPy' in sys.version:
            self.assertTrue(_PYPY)
        else:
            self.assertFalse(_PYPY)



@comparable
class Comparable(object):
    """
    Objects that can be compared to each other, but not others.
    """
    def __init__(self, value):
        self.value = value


    def __cmp__(self, other):
        if not isinstance(other, Comparable):
            return NotImplemented
        return cmp(self.value, other.value)



class ComparableTests(unittest.SynchronousTestCase):
    """
    L{comparable} decorated classes emulate Python 2's C{__cmp__} semantics.
    """

    def test_equality(self):
        """
        Instances of a class that is decorated by C{comparable} support
        equality comparisons.
        """
        # Make explicitly sure we're using ==:
        self.assertTrue(Comparable(1) == Comparable(1))
        self.assertFalse(Comparable(2) == Comparable(1))


    def test_nonEquality(self):
        """
        Instances of a class that is decorated by C{comparable} support
        inequality comparisons.
        """
        # Make explicitly sure we're using !=:
        self.assertFalse(Comparable(1) != Comparable(1))
        self.assertTrue(Comparable(2) != Comparable(1))


    def test_greaterThan(self):
        """
        Instances of a class that is decorated by C{comparable} support
        greater-than comparisons.
        """
        self.assertTrue(Comparable(2) > Comparable(1))
        self.assertFalse(Comparable(0) > Comparable(3))


    def test_greaterThanOrEqual(self):
        """
        Instances of a class that is decorated by C{comparable} support
        greater-than-or-equal comparisons.
        """
        self.assertTrue(Comparable(1) >= Comparable(1))
        self.assertTrue(Comparable(2) >= Comparable(1))
        self.assertFalse(Comparable(0) >= Comparable(3))


    def test_lessThan(self):
        """
        Instances of a class that is decorated by C{comparable} support
        less-than comparisons.
        """
        self.assertTrue(Comparable(0) < Comparable(3))
        self.assertFalse(Comparable(2) < Comparable(0))


    def test_lessThanOrEqual(self):
        """
        Instances of a class that is decorated by C{comparable} support
        less-than-or-equal comparisons.
        """
        self.assertTrue(Comparable(3) <= Comparable(3))
        self.assertTrue(Comparable(0) <= Comparable(3))
        self.assertFalse(Comparable(2) <= Comparable(0))



class Python3ComparableTests(unittest.SynchronousTestCase):
    """
    Python 3-specific functionality of C{comparable}.
    """

    def test_notImplementedEquals(self):
        """
        Instances of a class that is decorated by C{comparable} support
        returning C{NotImplemented} from C{__eq__} if it is returned by the
        underlying C{__cmp__} call.
        """
        self.assertEqual(Comparable(1).__eq__(object()), NotImplemented)


    def test_notImplementedNotEquals(self):
        """
        Instances of a class that is decorated by C{comparable} support
        returning C{NotImplemented} from C{__ne__} if it is returned by the
        underlying C{__cmp__} call.
        """
        self.assertEqual(Comparable(1).__ne__(object()), NotImplemented)


    def test_notImplementedGreaterThan(self):
        """
        Instances of a class that is decorated by C{comparable} support
        returning C{NotImplemented} from C{__gt__} if it is returned by the
        underlying C{__cmp__} call.
        """
        self.assertEqual(Comparable(1).__gt__(object()), NotImplemented)


    def test_notImplementedLessThan(self):
        """
        Instances of a class that is decorated by C{comparable} support
        returning C{NotImplemented} from C{__lt__} if it is returned by the
        underlying C{__cmp__} call.
        """
        self.assertEqual(Comparable(1).__lt__(object()), NotImplemented)


    def test_notImplementedGreaterThanEquals(self):
        """
        Instances of a class that is decorated by C{comparable} support
        returning C{NotImplemented} from C{__ge__} if it is returned by the
        underlying C{__cmp__} call.
        """
        self.assertEqual(Comparable(1).__ge__(object()), NotImplemented)


    def test_notImplementedLessThanEquals(self):
        """
        Instances of a class that is decorated by C{comparable} support
        returning C{NotImplemented} from C{__le__} if it is returned by the
        underlying C{__cmp__} call.
        """
        self.assertEqual(Comparable(1).__le__(object()), NotImplemented)

if not _PY3:
    # On Python 2, we just use __cmp__ directly, so checking detailed
    # comparison methods doesn't makes sense.
    Python3ComparableTests.skip = "Python 3 only."



class CmpTests(unittest.SynchronousTestCase):
    """
    L{cmp} should behave like the built-in Python 2 C{cmp}.
    """

    def test_equals(self):
        """
        L{cmp} returns 0 for equal objects.
        """
        self.assertEqual(cmp(u"a", u"a"), 0)
        self.assertEqual(cmp(1, 1), 0)
        self.assertEqual(cmp([1], [1]), 0)


    def test_greaterThan(self):
        """
        L{cmp} returns 1 if its first argument is bigger than its second.
        """
        self.assertEqual(cmp(4, 0), 1)
        self.assertEqual(cmp(b"z", b"a"), 1)


    def test_lessThan(self):
        """
        L{cmp} returns -1 if its first argument is smaller than its second.
        """
        self.assertEqual(cmp(0.1, 2.3), -1)
        self.assertEqual(cmp(b"a", b"d"), -1)



class StringTests(unittest.SynchronousTestCase):
    """
    Compatibility functions and types for strings.
    """

    def assertNativeString(self, original, expected):
        """
        Raise an exception indicating a failed test if the output of
        C{nativeString(original)} is unequal to the expected string, or is not
        a native string.
        """
        self.assertEqual(nativeString(original), expected)
        self.assertIsInstance(nativeString(original), str)


    def test_nonASCIIBytesToString(self):
        """
        C{nativeString} raises a C{UnicodeError} if input bytes are not ASCII
        decodable.
        """
        self.assertRaises(UnicodeError, nativeString, b"\xFF")


    def test_nonASCIIUnicodeToString(self):
        """
        C{nativeString} raises a C{UnicodeError} if input Unicode is not ASCII
        encodable.
        """
        self.assertRaises(UnicodeError, nativeString, u"\u1234")


    def test_bytesToString(self):
        """
        C{nativeString} converts bytes to the native string format, assuming
        an ASCII encoding if applicable.
        """
        self.assertNativeString(b"hello", "hello")


    def test_unicodeToString(self):
        """
        C{nativeString} converts unicode to the native string format, assuming
        an ASCII encoding if applicable.
        """
        self.assertNativeString(u"Good day", "Good day")


    def test_stringToString(self):
        """
        C{nativeString} leaves native strings as native strings.
        """
        self.assertNativeString("Hello!", "Hello!")


    def test_unexpectedType(self):
        """
        C{nativeString} raises a C{TypeError} if given an object that is not a
        string of some sort.
        """
        self.assertRaises(TypeError, nativeString, 1)


    def test_unicode(self):
        """
        C{compat.unicode} is C{str} on Python 3, C{unicode} on Python 2.
        """
        if _PY3:
            expected = str
        else:
            expected = unicode
        self.assertIs(unicodeCompat, expected)


    def test_nativeStringIO(self):
        """
        L{NativeStringIO} is a file-like object that stores native strings in
        memory.
        """
        f = NativeStringIO()
        f.write("hello")
        f.write(" there")
        self.assertEqual(f.getvalue(), "hello there")



class NetworkStringTests(unittest.SynchronousTestCase):
    """
    Tests for L{networkString}.
    """
    def test_bytes(self):
        """
        L{networkString} returns a C{bytes} object passed to it unmodified.
        """
        self.assertEqual(b"foo", networkString(b"foo"))


    def test_bytesOutOfRange(self):
        """
        L{networkString} raises C{UnicodeError} if passed a C{bytes} instance
        containing bytes not used by ASCII.
        """
        self.assertRaises(
            UnicodeError, networkString, u"\N{SNOWMAN}".encode('utf-8'))
    if _PY3:
        test_bytes.skip = test_bytesOutOfRange.skip = (
            "Bytes behavior of networkString only provided on Python 2.")


    def test_unicode(self):
        """
        L{networkString} returns a C{unicode} object passed to it encoded into
        a C{bytes} instance.
        """
        self.assertEqual(b"foo", networkString(u"foo"))


    def test_unicodeOutOfRange(self):
        """
        L{networkString} raises L{UnicodeError} if passed a C{unicode} instance
        containing characters not encodable in ASCII.
        """
        self.assertRaises(
            UnicodeError, networkString, u"\N{SNOWMAN}")
    if not _PY3:
        test_unicode.skip = test_unicodeOutOfRange.skip = (
            "Unicode behavior of networkString only provided on Python 3.")


    def test_nonString(self):
        """
        L{networkString} raises L{TypeError} if passed a non-string object or
        the wrong type of string object.
        """
        self.assertRaises(TypeError, networkString, object())
        if _PY3:
            self.assertRaises(TypeError, networkString, b"bytes")
        else:
            self.assertRaises(TypeError, networkString, u"text")



class ReraiseTests(unittest.SynchronousTestCase):
    """
    L{reraise} re-raises exceptions on both Python 2 and Python 3.
    """

    def test_reraiseWithNone(self):
        """
        Calling L{reraise} with an exception instance and a traceback of
        L{None} re-raises it with a new traceback.
        """
        try:
            1/0
        except:
            typ, value, tb = sys.exc_info()
        try:
            reraise(value, None)
        except:
            typ2, value2, tb2 = sys.exc_info()
            self.assertEqual(typ2, ZeroDivisionError)
            self.assertIs(value, value2)
            self.assertNotEqual(traceback.format_tb(tb)[-1],
                                traceback.format_tb(tb2)[-1])
        else:
            self.fail("The exception was not raised.")


    def test_reraiseWithTraceback(self):
        """
        Calling L{reraise} with an exception instance and a traceback
        re-raises the exception with the given traceback.
        """
        try:
            1/0
        except:
            typ, value, tb = sys.exc_info()
        try:
            reraise(value, tb)
        except:
            typ2, value2, tb2 = sys.exc_info()
            self.assertEqual(typ2, ZeroDivisionError)
            self.assertIs(value, value2)
            self.assertEqual(traceback.format_tb(tb)[-1],
                             traceback.format_tb(tb2)[-1])
        else:
            self.fail("The exception was not raised.")



class Python3BytesTests(unittest.SynchronousTestCase):
    """
    Tests for L{iterbytes}, L{intToBytes}, L{lazyByteSlice}.
    """

    def test_iteration(self):
        """
        When L{iterbytes} is called with a bytestring, the returned object
        can be iterated over, resulting in the individual bytes of the
        bytestring.
        """
        input = b"abcd"
        result = list(iterbytes(input))
        self.assertEqual(result, [b'a', b'b', b'c', b'd'])


    def test_intToBytes(self):
        """
        When L{intToBytes} is called with an integer, the result is an
        ASCII-encoded string representation of the number.
        """
        self.assertEqual(intToBytes(213), b"213")


    def test_lazyByteSliceNoOffset(self):
        """
        L{lazyByteSlice} called with some bytes returns a semantically equal
        version of these bytes.
        """
        data = b'123XYZ'
        self.assertEqual(bytes(lazyByteSlice(data)), data)


    def test_lazyByteSliceOffset(self):
        """
        L{lazyByteSlice} called with some bytes and an offset returns a
        semantically equal version of these bytes starting at the given offset.
        """
        data = b'123XYZ'
        self.assertEqual(bytes(lazyByteSlice(data, 2)), data[2:])


    def test_lazyByteSliceOffsetAndLength(self):
        """
        L{lazyByteSlice} called with some bytes, an offset and a length returns
        a semantically equal version of these bytes starting at the given
        offset, up to the given length.
        """
        data = b'123XYZ'
        self.assertEqual(bytes(lazyByteSlice(data, 2, 3)), data[2:5])



class BytesEnvironTests(unittest.TestCase):
    """
    Tests for L{BytesEnviron}.
    """
    def test_alwaysBytes(self):
        """
        The output of L{BytesEnviron} should always be a L{dict} with L{bytes}
        values and L{bytes} keys.
        """
        result = bytesEnviron()
        types = set()

        for key, val in iteritems(result):
            types.add(type(key))
            types.add(type(val))

        self.assertEqual(list(types), [bytes])



class OrderedDictTests(unittest.TestCase):
    """
    Tests for L{twisted.python.compat.OrderedDict}.
    """
    def test_deprecated(self):
        """
        L{twisted.python.compat.OrderedDict} is deprecated.
        """
        from twisted.python.compat import OrderedDict
        OrderedDict # Shh pyflakes

        currentWarnings = self.flushWarnings(offendingFunctions=[
            self.test_deprecated])
        self.assertEqual(
            currentWarnings[0]['message'],
            "twisted.python.compat.OrderedDict was deprecated in Twisted "
            "15.5.0: Use collections.OrderedDict instead.")
        self.assertEqual(currentWarnings[0]['category'], DeprecationWarning)
        self.assertEqual(len(currentWarnings), 1)



class CoercedUnicodeTests(unittest.TestCase):
    """
    Tests for L{twisted.python.compat._coercedUnicode}.
    """

    def test_unicodeASCII(self):
        """
        Unicode strings with ASCII code points are unchanged.
        """
        result = _coercedUnicode(u'text')
        self.assertEqual(result, u'text')
        self.assertIsInstance(result, unicodeCompat)


    def test_unicodeNonASCII(self):
        """
        Unicode strings with non-ASCII code points are unchanged.
        """
        result = _coercedUnicode(u'\N{SNOWMAN}')
        self.assertEqual(result, u'\N{SNOWMAN}')
        self.assertIsInstance(result, unicodeCompat)


    def test_nativeASCII(self):
        """
        Native strings with ASCII code points are unchanged.

        On Python 2, this verifies that ASCII-only byte strings are accepted,
        whereas for Python 3 it is identical to L{test_unicodeASCII}.
        """
        result = _coercedUnicode('text')
        self.assertEqual(result, u'text')
        self.assertIsInstance(result, unicodeCompat)


    def test_bytesPy3(self):
        """
        Byte strings are not accceptable in Python 3.
        """
        exc = self.assertRaises(TypeError, _coercedUnicode, b'bytes')
        self.assertEqual(str(exc), "Expected str not b'bytes' (bytes)")
    if not _PY3:
        test_bytesPy3.skip = (
            "Bytes behavior of _coercedUnicode only provided on Python 2.")


    def test_bytesNonASCII(self):
        """
        Byte strings with non-ASCII code points raise an exception.
        """
        self.assertRaises(UnicodeError, _coercedUnicode, b'\xe2\x98\x83')
    if _PY3:
        test_bytesNonASCII.skip = (
            "Bytes behavior of _coercedUnicode only provided on Python 2.")



class UnichrTests(unittest.TestCase):
    """
    Tests for L{unichr}.
    """

    def test_unichr(self):
        """
        unichar exists and returns a unicode string with the given code point.
        """
        self.assertEqual(unichr(0x2603), u"\N{SNOWMAN}")


class RawInputTests(unittest.TestCase):
    """
    Tests for L{raw_input}
    """
    def test_raw_input(self):
        """
        L{twisted.python.compat.raw_input}
        """
        class FakeStdin:
            def readline(self):
                return "User input\n"

        class FakeStdout:
            data = ""
            def write(self, data):
                self.data += data

        self.patch(sys, "stdin", FakeStdin())
        stdout = FakeStdout()
        self.patch(sys, "stdout", stdout)
        self.assertEqual(raw_input("Prompt"), "User input")
        self.assertEqual(stdout.data, "Prompt")



class FutureBytesReprTests(unittest.TestCase):
    """
    Tests for L{twisted.python.compat._bytesRepr}.
    """

    def test_bytesReprNotBytes(self):
        """
        L{twisted.python.compat._bytesRepr} raises a
        L{TypeError} when called any object that is not an instance of
        L{bytes}.
        """
        exc = self.assertRaises(TypeError, _bytesRepr, ["not bytes"])
        self.assertEquals(str(exc), "Expected bytes not ['not bytes']")


    def test_bytesReprPrefix(self):
        """
        L{twisted.python.compat._bytesRepr} always prepends
        ``b`` to the returned repr on both Python 2 and 3.
        """
        self.assertEqual(_bytesRepr(b'\x00'), "b'\\x00'")

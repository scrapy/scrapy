# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.names.rfc1982}.
"""

from __future__ import division, absolute_import

import calendar
from datetime import datetime
from functools import partial

from twisted.names._rfc1982 import SerialNumber
from twisted.trial import unittest



class SerialNumberTests(unittest.TestCase):
    """
    Tests for L{SerialNumber}.
    """

    def test_serialBitsDefault(self):
        """
        L{SerialNumber.serialBits} has default value 32.
        """
        self.assertEqual(SerialNumber(1)._serialBits, 32)


    def test_serialBitsOverride(self):
        """
        L{SerialNumber.__init__} accepts a C{serialBits} argument whose value is
        assigned to L{SerialNumber.serialBits}.
        """
        self.assertEqual(SerialNumber(1, serialBits=8)._serialBits, 8)


    def test_repr(self):
        """
        L{SerialNumber.__repr__} returns a string containing number and
        serialBits.
        """
        self.assertEqual(
            '<SerialNumber number=123 serialBits=32>',
            repr(SerialNumber(123, serialBits=32))
        )


    def test_str(self):
        """
        L{SerialNumber.__str__} returns a string representation of the current
        value.
        """
        self.assertEqual(str(SerialNumber(123)), '123')


    def test_int(self):
        """
        L{SerialNumber.__int__} returns an integer representation of the current
        value.
        """
        self.assertEqual(int(SerialNumber(123)), 123)


    def test_hash(self):
        """
        L{SerialNumber.__hash__} allows L{SerialNumber} instances to be hashed
        for use as dictionary keys.
        """
        self.assertEqual(hash(SerialNumber(1)), hash(SerialNumber(1)))
        self.assertNotEqual(hash(SerialNumber(1)), hash(SerialNumber(2)))


    def test_convertOtherSerialBitsMismatch(self):
        """
        L{SerialNumber._convertOther} raises L{TypeError} if the other
        SerialNumber instance has a different C{serialBits} value.
        """
        s1 = SerialNumber(0, serialBits=8)
        s2 = SerialNumber(0, serialBits=16)

        self.assertRaises(
            TypeError,
            s1._convertOther,
            s2
        )


    def test_eq(self):
        """
        L{SerialNumber.__eq__} provides rich equality comparison.
        """
        self.assertEqual(SerialNumber(1), SerialNumber(1))


    def test_eqForeignType(self):
        """
        == comparison of L{SerialNumber} with a non-L{SerialNumber} instance
        raises L{TypeError}.
        """
        self.assertRaises(TypeError, lambda: SerialNumber(1) == object())


    def test_ne(self):
        """
        L{SerialNumber.__ne__} provides rich equality comparison.
        """
        self.assertFalse(SerialNumber(1) != SerialNumber(1))
        self.assertNotEqual(SerialNumber(1), SerialNumber(2))


    def test_neForeignType(self):
        """
        != comparison of L{SerialNumber} with a non-L{SerialNumber} instance
        raises L{TypeError}.
        """
        self.assertRaises(TypeError, lambda: SerialNumber(1) != object())


    def test_le(self):
        """
        L{SerialNumber.__le__} provides rich <= comparison.
        """
        self.assertTrue(SerialNumber(1) <= SerialNumber(1))
        self.assertTrue(SerialNumber(1) <= SerialNumber(2))


    def test_leForeignType(self):
        """
        <= comparison of L{SerialNumber} with a non-L{SerialNumber} instance
        raises L{TypeError}.
        """
        self.assertRaises(TypeError, lambda: SerialNumber(1) <= object())


    def test_ge(self):
        """
        L{SerialNumber.__ge__} provides rich >= comparison.
        """
        self.assertTrue(SerialNumber(1) >= SerialNumber(1))
        self.assertTrue(SerialNumber(2) >= SerialNumber(1))


    def test_geForeignType(self):
        """
        >= comparison of L{SerialNumber} with a non-L{SerialNumber} instance
        raises L{TypeError}.
        """
        self.assertRaises(TypeError, lambda: SerialNumber(1) >= object())


    def test_lt(self):
        """
        L{SerialNumber.__lt__} provides rich < comparison.
        """
        self.assertTrue(SerialNumber(1) < SerialNumber(2))


    def test_ltForeignType(self):
        """
        < comparison of L{SerialNumber} with a non-L{SerialNumber} instance
        raises L{TypeError}.
        """
        self.assertRaises(TypeError, lambda: SerialNumber(1) < object())


    def test_gt(self):
        """
        L{SerialNumber.__gt__} provides rich > comparison.
        """
        self.assertTrue(SerialNumber(2) > SerialNumber(1))


    def test_gtForeignType(self):
        """
        > comparison of L{SerialNumber} with a non-L{SerialNumber} instance
          raises L{TypeError}.
        """
        self.assertRaises(TypeError, lambda: SerialNumber(2) > object())


    def test_add(self):
        """
        L{SerialNumber.__add__} allows L{SerialNumber} instances to be summed.
        """
        self.assertEqual(SerialNumber(1) + SerialNumber(1), SerialNumber(2))


    def test_addForeignType(self):
        """
        Addition of L{SerialNumber} with a non-L{SerialNumber} instance raises
        L{TypeError}.
        """
        self.assertRaises(TypeError, lambda: SerialNumber(1) + object())


    def test_addOutOfRangeHigh(self):
        """
        L{SerialNumber} cannot be added with other SerialNumber values larger
        than C{_maxAdd}.
        """
        maxAdd = SerialNumber(1)._maxAdd
        self.assertRaises(
            ArithmeticError,
            lambda: SerialNumber(1) + SerialNumber(maxAdd + 1))


    def test_maxVal(self):
        """
        L{SerialNumber.__add__} returns a wrapped value when s1 plus the s2
        would result in a value greater than the C{maxVal}.
        """
        s = SerialNumber(1)
        maxVal = s._halfRing + s._halfRing - 1
        maxValPlus1 = maxVal + 1
        self.assertTrue(SerialNumber(maxValPlus1) > SerialNumber(maxVal))
        self.assertEqual(SerialNumber(maxValPlus1), SerialNumber(0))


    def test_fromRFC4034DateString(self):
        """
        L{SerialNumber.fromRFC4034DateString} accepts a datetime string argument
        of the form 'YYYYMMDDhhmmss' and returns an L{SerialNumber} instance
        whose value is the unix timestamp corresponding to that UTC date.
        """
        self.assertEqual(
            SerialNumber(1325376000),
            SerialNumber.fromRFC4034DateString('20120101000000')
        )


    def test_toRFC4034DateString(self):
        """
        L{DateSerialNumber.toRFC4034DateString} interprets the current value as
        a unix timestamp and returns a date string representation of that date.
        """
        self.assertEqual(
            '20120101000000',
            SerialNumber(1325376000).toRFC4034DateString()
        )


    def test_unixEpoch(self):
        """
        L{SerialNumber.toRFC4034DateString} stores 32bit timestamps relative to
        the UNIX epoch.
        """
        self.assertEqual(
            SerialNumber(0).toRFC4034DateString(),
            '19700101000000'
        )


    def test_Y2106Problem(self):
        """
        L{SerialNumber} wraps unix timestamps in the year 2106.
        """
        self.assertEqual(
            SerialNumber(-1).toRFC4034DateString(),
            '21060207062815'
        )


    def test_Y2038Problem(self):
        """
        L{SerialNumber} raises ArithmeticError when used to add dates more than
        68 years in the future.
        """
        maxAddTime = calendar.timegm(
            datetime(2038, 1, 19, 3, 14, 7).utctimetuple())

        self.assertEqual(
            maxAddTime,
            SerialNumber(0)._maxAdd,
        )

        self.assertRaises(
            ArithmeticError,
            lambda: SerialNumber(0) + SerialNumber(maxAddTime + 1))



def assertUndefinedComparison(testCase, s1, s2):
    """
    A custom assertion for L{SerialNumber} values that cannot be meaningfully
    compared.

    "Note that there are some pairs of values s1 and s2 for which s1 is not
    equal to s2, but for which s1 is neither greater than, nor less than, s2.
    An attempt to use these ordering operators on such pairs of values produces
    an undefined result."

    @see: U{https://tools.ietf.org/html/rfc1982#section-3.2}

    @param testCase: The L{unittest.TestCase} on which to call assertion
        methods.
    @type testCase: L{unittest.TestCase}

    @param s1: The first value to compare.
    @type s1: L{SerialNumber}

    @param s2: The second value to compare.
    @type s2: L{SerialNumber}
    """
    testCase.assertFalse(s1 == s2)
    testCase.assertFalse(s1 <= s2)
    testCase.assertFalse(s1 < s2)
    testCase.assertFalse(s1 > s2)
    testCase.assertFalse(s1 >= s2)



serialNumber2 = partial(SerialNumber, serialBits=2)



class SerialNumber2BitTests(unittest.TestCase):
    """
    Tests for correct answers to example calculations in RFC1982 5.1.

    The simplest meaningful serial number space has SERIAL_BITS == 2.  In this
    space, the integers that make up the serial number space are 0, 1, 2, and 3.
    That is, 3 == 2^SERIAL_BITS - 1.

    https://tools.ietf.org/html/rfc1982#section-5.1
    """
    def test_maxadd(self):
        """
        In this space, the largest integer that it is meaningful to add to a
        sequence number is 2^(SERIAL_BITS - 1) - 1, or 1.
        """
        self.assertEqual(SerialNumber(0, serialBits=2)._maxAdd, 1)


    def test_add(self):
        """
        Then, as defined 0+1 == 1, 1+1 == 2, 2+1 == 3, and 3+1 == 0.
        """
        self.assertEqual(serialNumber2(0) + serialNumber2(1), serialNumber2(1))
        self.assertEqual(serialNumber2(1) + serialNumber2(1), serialNumber2(2))
        self.assertEqual(serialNumber2(2) + serialNumber2(1), serialNumber2(3))
        self.assertEqual(serialNumber2(3) + serialNumber2(1), serialNumber2(0))


    def test_gt(self):
        """
        Further, 1 > 0, 2 > 1, 3 > 2, and 0 > 3.
        """
        self.assertTrue(serialNumber2(1) > serialNumber2(0))
        self.assertTrue(serialNumber2(2) > serialNumber2(1))
        self.assertTrue(serialNumber2(3) > serialNumber2(2))
        self.assertTrue(serialNumber2(0) > serialNumber2(3))


    def test_undefined(self):
        """
        It is undefined whether 2 > 0 or 0 > 2, and whether 1 > 3 or 3 > 1.
        """
        assertUndefinedComparison(self, serialNumber2(2), serialNumber2(0))
        assertUndefinedComparison(self, serialNumber2(0), serialNumber2(2))
        assertUndefinedComparison(self, serialNumber2(1), serialNumber2(3))
        assertUndefinedComparison(self, serialNumber2(3), serialNumber2(1))



serialNumber8 = partial(SerialNumber, serialBits=8)



class SerialNumber8BitTests(unittest.TestCase):
    """
    Tests for correct answers to example calculations in RFC1982 5.2.

    Consider the case where SERIAL_BITS == 8.  In this space the integers that
    make up the serial number space are 0, 1, 2, ... 254, 255.  255 ==
    2^SERIAL_BITS - 1.

    https://tools.ietf.org/html/rfc1982#section-5.2
    """

    def test_maxadd(self):
        """
        In this space, the largest integer that it is meaningful to add to a
        sequence number is 2^(SERIAL_BITS - 1) - 1, or 127.
        """
        self.assertEqual(SerialNumber(0, serialBits=8)._maxAdd, 127)


    def test_add(self):
        """
        Addition is as expected in this space, for example: 255+1 == 0,
        100+100 == 200, and 200+100 == 44.
        """
        self.assertEqual(
            serialNumber8(255) + serialNumber8(1), serialNumber8(0))
        self.assertEqual(
            serialNumber8(100) + serialNumber8(100), serialNumber8(200))
        self.assertEqual(
            serialNumber8(200) + serialNumber8(100), serialNumber8(44))


    def test_gt(self):
        """
        Comparison is more interesting, 1 > 0, 44 > 0, 100 > 0, 100 > 44,
        200 > 100, 255 > 200, 0 > 255, 100 > 255, 0 > 200, and 44 > 200.
        """
        self.assertTrue(serialNumber8(1) > serialNumber8(0))
        self.assertTrue(serialNumber8(44) > serialNumber8(0))
        self.assertTrue(serialNumber8(100) > serialNumber8(0))
        self.assertTrue(serialNumber8(100) > serialNumber8(44))
        self.assertTrue(serialNumber8(200) > serialNumber8(100))
        self.assertTrue(serialNumber8(255) > serialNumber8(200))
        self.assertTrue(serialNumber8(100) > serialNumber8(255))
        self.assertTrue(serialNumber8(0) > serialNumber8(200))
        self.assertTrue(serialNumber8(44) > serialNumber8(200))


    def test_surprisingAddition(self):
        """
        Note that 100+100 > 100, but that (100+100)+100 < 100.  Incrementing a
        serial number can cause it to become "smaller".  Of course, incrementing
        by a smaller number will allow many more increments to be made before
        this occurs.  However this is always something to be aware of, it can
        cause surprising errors, or be useful as it is the only defined way to
        actually cause a serial number to decrease.
        """
        self.assertTrue(
            serialNumber8(100) + serialNumber8(100) > serialNumber8(100))
        self.assertTrue(
            serialNumber8(100) + serialNumber8(100) + serialNumber8(100)
            < serialNumber8(100))


    def test_undefined(self):
        """
        The pairs of values 0 and 128, 1 and 129, 2 and 130, etc, to 127 and 255
        are not equal, but in each pair, neither number is defined as being
        greater than, or less than, the other.
        """
        assertUndefinedComparison(self, serialNumber8(0), serialNumber8(128))
        assertUndefinedComparison(self, serialNumber8(1), serialNumber8(129))
        assertUndefinedComparison(self, serialNumber8(2), serialNumber8(130))
        assertUndefinedComparison(self, serialNumber8(127), serialNumber8(255))

# -*- test-case-name: twisted.names.test.test_rfc1982 -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Utilities for handling RFC1982 Serial Number Arithmetic.

@see: U{http://tools.ietf.org/html/rfc1982}

@var RFC4034_TIME_FORMAT: RRSIG Time field presentation format. The Signature
   Expiration Time and Inception Time field values MUST be represented either
   as an unsigned decimal integer indicating seconds since 1 January 1970
   00:00:00 UTC, or in the form YYYYMMDDHHmmSS in UTC. See U{RRSIG Presentation
   Format<https://tools.ietf.org/html/rfc4034#section-3.2>}
"""

from __future__ import division, absolute_import

import calendar
from datetime import datetime, timedelta

from twisted.python.compat import nativeString
from twisted.python.util import FancyStrMixin


RFC4034_TIME_FORMAT = '%Y%m%d%H%M%S'



class SerialNumber(FancyStrMixin, object):
    """
    An RFC1982 Serial Number.

    This class implements RFC1982 DNS Serial Number Arithmetic.

    SNA is used in DNS and specifically in DNSSEC as defined in RFC4034 in the
    DNSSEC Signature Expiration and Inception Fields.

    @see: U{https://tools.ietf.org/html/rfc1982}
    @see: U{https://tools.ietf.org/html/rfc4034}

    @ivar _serialBits: See C{serialBits} of L{__init__}.
    @ivar _number: See C{number} of L{__init__}.
    @ivar _modulo: The value at which wrapping will occur.
    @ivar _halfRing: Half C{_modulo}. If another L{SerialNumber} value is larger
        than this, it would lead to a wrapped value which is larger than the
        first and comparisons are therefore ambiguous.
    @ivar _maxAdd: Half C{_modulo} plus 1. If another L{SerialNumber} value is
        larger than this, it would lead to a wrapped value which is larger than
        the first. Comparisons with the original value would therefore be
        ambiguous.
    """

    showAttributes = (
        ('_number', 'number', '%d'),
        ('_serialBits', 'serialBits', '%d'),
    )

    def __init__(self, number, serialBits=32):
        """
        Construct an L{SerialNumber} instance.

        @param number: An L{int} which will be stored as the modulo
            C{number % 2 ^ serialBits}
        @type number: L{int}

        @param serialBits: The size of the serial number space. The power of two
            which results in one larger than the largest integer corresponding
            to a serial number value.
        @type serialBits: L{int}
        """
        self._serialBits = serialBits
        self._modulo = 2 ** serialBits
        self._halfRing = 2 ** (serialBits - 1)
        self._maxAdd = 2 ** (serialBits - 1) - 1
        self._number = int(number) % self._modulo


    def _convertOther(self, other):
        """
        Check that a foreign object is suitable for use in the comparison or
        arithmetic magic methods of this L{SerialNumber} instance. Raise
        L{TypeError} if not.

        @param other: The foreign L{object} to be checked.
        @return: C{other} after compatibility checks and possible coercion.
        @raises: L{TypeError} if C{other} is not compatible.
        """
        if not isinstance(other, SerialNumber):
            raise TypeError(
                'cannot compare or combine %r and %r' % (self, other))

        if self._serialBits != other._serialBits:
            raise TypeError(
                'cannot compare or combine SerialNumber instances with '
                'different serialBits. %r and %r' % (self, other))

        return other


    def __str__(self):
        """
        Return a string representation of this L{SerialNumber} instance.

        @rtype: L{nativeString}
        """
        return nativeString('%d' % (self._number,))


    def __int__(self):
        """
        @return: The integer value of this L{SerialNumber} instance.
        @rtype: L{int}
        """
        return self._number


    def __eq__(self, other):
        """
        Allow rich equality comparison with another L{SerialNumber} instance.

        @type other: L{SerialNumber}
        """
        other = self._convertOther(other)
        return other._number == self._number


    def __ne__(self, other):
        """
        Allow rich equality comparison with another L{SerialNumber} instance.

        @type other: L{SerialNumber}
        """
        return not self.__eq__(other)


    def __lt__(self, other):
        """
        Allow I{less than} comparison with another L{SerialNumber} instance.

        @type other: L{SerialNumber}
        """
        other = self._convertOther(other)
        return (
            (self._number < other._number
             and (other._number - self._number) < self._halfRing)
            or
            (self._number > other._number
             and (self._number - other._number) > self._halfRing)
        )


    def __gt__(self, other):
        """
        Allow I{greater than} comparison with another L{SerialNumber} instance.

        @type other: L{SerialNumber}
        @rtype: L{bool}
        """
        other = self._convertOther(other)
        return (
            (self._number < other._number
             and (other._number - self._number) > self._halfRing)
            or
            (self._number > other._number
             and (self._number - other._number) < self._halfRing)
        )


    def __le__(self, other):
        """
        Allow I{less than or equal} comparison with another L{SerialNumber}
        instance.

        @type other: L{SerialNumber}
        @rtype: L{bool}
        """
        other = self._convertOther(other)
        return self == other or self < other


    def __ge__(self, other):
        """
        Allow I{greater than or equal} comparison with another L{SerialNumber}
        instance.

        @type other: L{SerialNumber}
        @rtype: L{bool}
        """
        other = self._convertOther(other)
        return self == other or self > other


    def __add__(self, other):
        """
        Allow I{addition} with another L{SerialNumber} instance.

        Serial numbers may be incremented by the addition of a positive
        integer n, where n is taken from the range of integers
        [0 .. (2^(SERIAL_BITS - 1) - 1)].  For a sequence number s, the
        result of such an addition, s', is defined as

        s' = (s + n) modulo (2 ^ SERIAL_BITS)

        where the addition and modulus operations here act upon values that are
        non-negative values of unbounded size in the usual ways of integer
        arithmetic.

        Addition of a value outside the range
        [0 .. (2^(SERIAL_BITS - 1) - 1)] is undefined.

        @see: U{http://tools.ietf.org/html/rfc1982#section-3.1}

        @type other: L{SerialNumber}
        @rtype: L{SerialNumber}
        @raises: L{ArithmeticError} if C{other} is more than C{_maxAdd}
            ie more than half the maximum value of this serial number.
        """
        other = self._convertOther(other)
        if other._number <= self._maxAdd:
            return SerialNumber(
                (self._number + other._number) % self._modulo,
                serialBits=self._serialBits)
        else:
            raise ArithmeticError(
                'value %r outside the range 0 .. %r' % (
                    other._number, self._maxAdd,))


    def __hash__(self):
        """
        Allow L{SerialNumber} instances to be hashed for use as L{dict} keys.

        @rtype: L{int}
        """
        return hash(self._number)


    @classmethod
    def fromRFC4034DateString(cls, utcDateString):
        """
        Create an L{SerialNumber} instance from a date string in format
        'YYYYMMDDHHMMSS' described in U{RFC4034
        3.2<https://tools.ietf.org/html/rfc4034#section-3.2>}.

        The L{SerialNumber} instance stores the date as a 32bit UNIX timestamp.

        @see: U{https://tools.ietf.org/html/rfc4034#section-3.1.5}

        @param utcDateString: A UTC date/time string of format I{YYMMDDhhmmss}
            which will be converted to seconds since the UNIX epoch.
        @type utcDateString: L{unicode}

        @return: An L{SerialNumber} instance containing the supplied date as a
            32bit UNIX timestamp.
        """
        parsedDate = datetime.strptime(utcDateString, RFC4034_TIME_FORMAT)
        secondsSinceEpoch = calendar.timegm(parsedDate.utctimetuple())
        return cls(secondsSinceEpoch, serialBits=32)


    def toRFC4034DateString(self):
        """
        Calculate a date by treating the current L{SerialNumber} value as a UNIX
        timestamp and return a date string in the format described in
        U{RFC4034 3.2<https://tools.ietf.org/html/rfc4034#section-3.2>}.

        @return: The date string.
        """
        # Can't use datetime.utcfromtimestamp, because it seems to overflow the
        # signed 32bit int used in the underlying C library. SNA is unsigned
        # and capable of handling all timestamps up to 2**32.
        d = datetime(1970, 1, 1) + timedelta(seconds=self._number)
        return nativeString(d.strftime(RFC4034_TIME_FORMAT))



__all__ = ['SerialNumber']

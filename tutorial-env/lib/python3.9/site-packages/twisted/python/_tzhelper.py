# -*- test-case-name: twisted.python.test.test_tzhelper -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Time zone utilities.
"""

from datetime import datetime as DateTime, timedelta as TimeDelta, tzinfo as TZInfo
from typing import Optional

__all__ = [
    "FixedOffsetTimeZone",
    "UTC",
]


class FixedOffsetTimeZone(TZInfo):
    """
    Represents a fixed timezone offset (without daylight saving time).

    @ivar name: A L{str} giving the name of this timezone; the name just
        includes how much time this offset represents.

    @ivar offset: A L{TimeDelta} giving the amount of time this timezone is
        offset.
    """

    def __init__(self, offset: TimeDelta, name: Optional[str] = None) -> None:
        """
        Construct a L{FixedOffsetTimeZone} with a fixed offset.

        @param offset: a delta representing the offset from UTC.
        @param name: A name to be given for this timezone.
        """
        self.offset = offset
        self.name = name

    @classmethod
    def fromSignHoursMinutes(
        cls, sign: str, hours: int, minutes: int
    ) -> "FixedOffsetTimeZone":
        """
        Construct a L{FixedOffsetTimeZone} from an offset described by sign
        ('+' or '-'), hours, and minutes.

        @note: For protocol compatibility with AMP, this method never uses 'Z'

        @param sign: A string describing the positive or negative-ness of the
            offset.
        @param hours: The number of hours in the offset.
        @param minutes: The number of minutes in the offset

        @return: A time zone with the given offset, and a name describing the
            offset.
        """
        name = "%s%02i:%02i" % (sign, hours, minutes)
        if sign == "-":
            hours = -hours
            minutes = -minutes
        elif sign != "+":
            raise ValueError(f"Invalid sign for timezone {sign!r}")
        return cls(TimeDelta(hours=hours, minutes=minutes), name)

    @classmethod
    def fromLocalTimeStamp(cls, timeStamp: float) -> "FixedOffsetTimeZone":
        """
        Create a time zone with a fixed offset corresponding to a time stamp in
        the system's locally configured time zone.
        """
        offset = DateTime.fromtimestamp(timeStamp) - DateTime.utcfromtimestamp(
            timeStamp
        )
        return cls(offset)

    def utcoffset(self, dt: Optional[DateTime]) -> TimeDelta:
        """
        Return the given timezone's offset from UTC.
        """
        return self.offset

    def dst(self, dt: Optional[DateTime]) -> TimeDelta:
        """
        Return a zero L{TimeDelta} for the daylight saving time
        offset, since there is never one.
        """
        return TimeDelta(0)

    def tzname(self, dt: Optional[DateTime]) -> str:
        """
        Return a string describing this timezone.
        """
        if self.name is not None:
            return self.name
        # XXX this is wrong; the tests are
        dt = DateTime.fromtimestamp(0, self)
        return dt.strftime("UTC%z")


UTC = FixedOffsetTimeZone.fromSignHoursMinutes("+", 0, 0)

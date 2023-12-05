# -*- test-case-name: twisted.positioning.test.test_base,twisted.positioning.test.test_sentence -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
"""
Generic positioning base classes.

@since: 14.0
"""


from functools import partial
from operator import attrgetter
from typing import ClassVar, Sequence

from zope.interface import implementer

from constantly import NamedConstant, Names  # type: ignore[import]

from twisted.positioning import ipositioning
from twisted.python.util import FancyEqMixin

MPS_PER_KNOT = 0.5144444444444444
MPS_PER_KPH = 0.27777777777777777
METERS_PER_FOOT = 0.3048


class Angles(Names):
    """
    The types of angles.

    @cvar LATITUDE: Angle representing a latitude of an object.
    @type LATITUDE: L{NamedConstant}

    @cvar LONGITUDE: Angle representing the longitude of an object.
    @type LONGITUDE: L{NamedConstant}

    @cvar HEADING: Angle representing the heading of an object.
    @type HEADING: L{NamedConstant}

    @cvar VARIATION: Angle representing a magnetic variation.
    @type VARIATION: L{NamedConstant}

    """

    LATITUDE = NamedConstant()
    LONGITUDE = NamedConstant()
    HEADING = NamedConstant()
    VARIATION = NamedConstant()


class Directions(Names):
    """
    The four cardinal directions (north, east, south, west).
    """

    NORTH = NamedConstant()
    EAST = NamedConstant()
    SOUTH = NamedConstant()
    WEST = NamedConstant()


@implementer(ipositioning.IPositioningReceiver)
class BasePositioningReceiver:
    """
    A base positioning receiver.

    This class would be a good base class for building positioning
    receivers. It implements the interface (so you don't have to) with stub
    methods.

    People who want to implement positioning receivers should subclass this
    class and override the specific callbacks they want to handle.
    """

    def timeReceived(self, time):
        """
        Implements L{IPositioningReceiver.timeReceived} stub.
        """

    def headingReceived(self, heading):
        """
        Implements L{IPositioningReceiver.headingReceived} stub.
        """

    def speedReceived(self, speed):
        """
        Implements L{IPositioningReceiver.speedReceived} stub.
        """

    def climbReceived(self, climb):
        """
        Implements L{IPositioningReceiver.climbReceived} stub.
        """

    def positionReceived(self, latitude, longitude):
        """
        Implements L{IPositioningReceiver.positionReceived} stub.
        """

    def positionErrorReceived(self, positionError):
        """
        Implements L{IPositioningReceiver.positionErrorReceived} stub.
        """

    def altitudeReceived(self, altitude):
        """
        Implements L{IPositioningReceiver.altitudeReceived} stub.
        """

    def beaconInformationReceived(self, beaconInformation):
        """
        Implements L{IPositioningReceiver.beaconInformationReceived} stub.
        """


class InvalidSentence(Exception):
    """
    An exception raised when a sentence is invalid.
    """


class InvalidChecksum(Exception):
    """
    An exception raised when the checksum of a sentence is invalid.
    """


class Angle(FancyEqMixin):
    """
    An object representing an angle.

    @cvar _RANGE_EXPRESSIONS: A collection of expressions for the allowable
        range for the angular value of a particular coordinate value.
    @type _RANGE_EXPRESSIONS: C{dict} of L{Angles} constants to callables
    @cvar _ANGLE_TYPE_NAMES: English names for angle types.
    @type _ANGLE_TYPE_NAMES: C{dict} of L{Angles} constants to C{str}
    """

    _RANGE_EXPRESSIONS = {
        Angles.LATITUDE: lambda latitude: -90.0 < latitude < 90.0,
        Angles.LONGITUDE: lambda longitude: -180.0 < longitude < 180.0,
        Angles.HEADING: lambda heading: 0 <= heading < 360,
        Angles.VARIATION: lambda variation: -180 < variation <= 180,
    }

    _ANGLE_TYPE_NAMES = {
        Angles.LATITUDE: "Latitude",
        Angles.LONGITUDE: "Longitude",
        Angles.VARIATION: "Variation",
        Angles.HEADING: "Heading",
    }

    compareAttributes: ClassVar[Sequence[str]] = (
        "angleType",
        "inDecimalDegrees",
    )

    def __init__(self, angle=None, angleType=None):
        """
        Initializes an angle.

        @param angle: The value of the angle in decimal degrees. (L{None} if
            unknown).
        @type angle: C{float} or L{None}

        @param angleType: A symbolic constant describing the angle type. Should
            be one of L{Angles} or {None} if unknown.

        @raises ValueError: If the angle type is not the default argument,
            but it is an unknown type (not in  C{Angle._RANGE_EXPRESSIONS}),
            or it is a known type but the supplied value was out of the
            allowable range for said type.
        """
        if angleType is not None and angleType not in self._RANGE_EXPRESSIONS:
            raise ValueError("Unknown angle type")

        if angle is not None and angleType is not None:
            rangeExpression = self._RANGE_EXPRESSIONS[angleType]
            if not rangeExpression(angle):
                template = "Angle {0} not in allowed range for type {1}"
                raise ValueError(template.format(angle, angleType))

        self.angleType = angleType
        self._angle = angle

    @property
    def inDecimalDegrees(self):
        """
        The value of this angle in decimal degrees. This value is immutable.

        @return: This angle expressed in decimal degrees, or L{None} if the
            angle is unknown.
        @rtype: C{float} (or L{None})
        """
        return self._angle

    @property
    def inDegreesMinutesSeconds(self):
        """
        The value of this angle as a degrees, minutes, seconds tuple. This
        value is immutable.

        @return: This angle expressed in degrees, minutes, seconds. L{None} if
            the angle is unknown.
        @rtype: 3-C{tuple} of C{int} (or L{None})
        """
        if self._angle is None:
            return None

        degrees = abs(int(self._angle))
        fractionalDegrees = abs(self._angle - int(self._angle))
        decimalMinutes = 60 * fractionalDegrees

        minutes = int(decimalMinutes)
        fractionalMinutes = decimalMinutes - int(decimalMinutes)
        decimalSeconds = 60 * fractionalMinutes

        return degrees, minutes, int(decimalSeconds)

    def setSign(self, sign):
        """
        Sets the sign of this angle.

        @param sign: The new sign. C{1} for positive and C{-1} for negative
            signs, respectively.
        @type sign: C{int}

        @raise ValueError: If the C{sign} parameter is not C{-1} or C{1}.
        """
        if sign not in (-1, 1):
            raise ValueError("bad sign (got %s, expected -1 or 1)" % sign)

        self._angle = sign * abs(self._angle)

    def __float__(self):
        """
        Returns this angle as a float.

        @return: The float value of this angle, expressed in degrees.
        @rtype: C{float}
        """
        return self._angle

    def __repr__(self) -> str:
        """
        Returns a string representation of this angle.

        @return: The string representation.
        @rtype: C{str}
        """
        return "<{s._angleTypeNameRepr} ({s._angleValueRepr})>".format(s=self)

    @property
    def _angleValueRepr(self):
        """
        Returns a string representation of the angular value of this angle.

        This is a helper function for the actual C{__repr__}.

        @return: The string representation.
        @rtype: C{str}
        """
        if self.inDecimalDegrees is not None:
            return "%s degrees" % round(self.inDecimalDegrees, 2)
        else:
            return "unknown value"

    @property
    def _angleTypeNameRepr(self):
        """
        Returns a string representation of the type of this angle.

        This is a helper function for the actual C{__repr__}.

        @return: The string representation.
        @rtype: C{str}
        """
        try:
            return self._ANGLE_TYPE_NAMES[self.angleType]
        except KeyError:
            return "Angle of unknown type"


class Heading(Angle):
    """
    The heading of a mobile object.

    @ivar variation: The (optional) magnetic variation.
        The sign of the variation is positive for variations towards the east
        (clockwise from north), and negative for variations towards the west
        (counterclockwise from north).
        If the variation is unknown or not applicable, this is L{None}.
    @type variation: C{Angle} or L{None}.
    @ivar correctedHeading: The heading, corrected for variation. If the
        variation is unknown (L{None}), is None. This attribute is read-only
        (its value is determined by the angle and variation attributes). The
        value is coerced to being between 0 (inclusive) and 360 (exclusive).
    """

    def __init__(self, angle=None, variation=None):
        """
        Initializes an angle with an optional variation.
        """
        Angle.__init__(self, angle, Angles.HEADING)
        self.variation = variation

    @classmethod
    def fromFloats(cls, angleValue=None, variationValue=None):
        """
        Constructs a Heading from the float values of the angle and variation.

        @param angleValue: The angle value of this heading.
        @type angleValue: C{float}
        @param variationValue: The value of the variation of this heading.
        @type variationValue: C{float}
        @return: A L{Heading} with the given values.
        """
        variation = Angle(variationValue, Angles.VARIATION)
        return cls(angleValue, variation)

    @property
    def correctedHeading(self):
        """
        Corrects the heading by the given variation. This is sometimes known as
        the true heading.

        @return: The heading, corrected by the variation. If the variation or
            the angle are unknown, returns L{None}.
        @rtype: C{float} or L{None}
        """
        if self._angle is None or self.variation is None:
            return None

        angle = (self.inDecimalDegrees - self.variation.inDecimalDegrees) % 360
        return Angle(angle, Angles.HEADING)

    def setSign(self, sign):
        """
        Sets the sign of the variation of this heading.

        @param sign: The new sign. C{1} for positive and C{-1} for negative
            signs, respectively.
        @type sign: C{int}

        @raise ValueError: If the C{sign} parameter is not C{-1} or C{1}.
        """
        if self.variation.inDecimalDegrees is None:
            raise ValueError("can't set the sign of an unknown variation")

        self.variation.setSign(sign)

    compareAttributes = list(Angle.compareAttributes) + ["variation"]

    def __repr__(self) -> str:
        """
        Returns a string representation of this angle.

        @return: The string representation.
        @rtype: C{str}
        """
        if self.variation is None:
            variationRepr = "unknown variation"
        else:
            variationRepr = repr(self.variation)

        return "<{} ({}, {})>".format(
            self._angleTypeNameRepr,
            self._angleValueRepr,
            variationRepr,
        )


class Coordinate(Angle):
    """
    A coordinate.

    @ivar angle: The value of the coordinate in decimal degrees, with the usual
        rules for sign (northern and eastern hemispheres are positive, southern
        and western hemispheres are negative).
    @type angle: C{float}
    """

    def __init__(self, angle, coordinateType=None):
        """
        Initializes a coordinate.

        @param angle: The angle of this coordinate in decimal degrees. The
            hemisphere is determined by the sign (north and east are positive).
            If this coordinate describes a latitude, this value must be within
            -90.0 and +90.0 (exclusive). If this value describes a longitude,
            this value must be within -180.0 and +180.0 (exclusive).
        @type angle: C{float}
        @param coordinateType: The coordinate type. One of L{Angles.LATITUDE},
            L{Angles.LONGITUDE} or L{None} if unknown.
        """
        if coordinateType not in [Angles.LATITUDE, Angles.LONGITUDE, None]:
            raise ValueError(
                "coordinateType must be one of Angles.LATITUDE, "
                "Angles.LONGITUDE or None, was {!r}".format(coordinateType)
            )

        Angle.__init__(self, angle, coordinateType)

    @property
    def hemisphere(self):
        """
        Gets the hemisphere of this coordinate.

        @return: A symbolic constant representing a hemisphere (one of
            L{Angles})
        """

        if self.angleType is Angles.LATITUDE:
            if self.inDecimalDegrees < 0:
                return Directions.SOUTH
            else:
                return Directions.NORTH
        elif self.angleType is Angles.LONGITUDE:
            if self.inDecimalDegrees < 0:
                return Directions.WEST
            else:
                return Directions.EAST
        else:
            raise ValueError("unknown coordinate type (cant find hemisphere)")


class Altitude(FancyEqMixin):
    """
    An altitude.

    @ivar inMeters: The altitude represented by this object, in meters. This
        attribute is read-only.
    @type inMeters: C{float}

    @ivar inFeet: As above, but expressed in feet.
    @type inFeet: C{float}
    """

    compareAttributes = ("inMeters",)

    def __init__(self, altitude):
        """
        Initializes an altitude.

        @param altitude: The altitude in meters.
        @type altitude: C{float}
        """
        self._altitude = altitude

    @property
    def inFeet(self):
        """
        Gets the altitude this object represents, in feet.

        @return: The altitude, expressed in feet.
        @rtype: C{float}
        """
        return self._altitude / METERS_PER_FOOT

    @property
    def inMeters(self):
        """
        Returns the altitude this object represents, in meters.

        @return: The altitude, expressed in feet.
        @rtype: C{float}
        """
        return self._altitude

    def __float__(self):
        """
        Returns the altitude represented by this object expressed in meters.

        @return: The altitude represented by this object, expressed in meters.
        @rtype: C{float}
        """
        return self._altitude

    def __repr__(self) -> str:
        """
        Returns a string representation of this altitude.

        @return: The string representation.
        @rtype: C{str}
        """
        return f"<Altitude ({self._altitude} m)>"


class _BaseSpeed(FancyEqMixin):
    """
    An object representing the abstract concept of the speed (rate of
    movement) of a mobile object.

    This primarily has behavior for converting between units and comparison.
    """

    compareAttributes = ("inMetersPerSecond",)

    def __init__(self, speed):
        """
        Initializes a speed.

        @param speed: The speed that this object represents, expressed in
            meters per second.
        @type speed: C{float}

        @raises ValueError: Raised if value was invalid for this particular
            kind of speed. Only happens in subclasses.
        """
        self._speed = speed

    @property
    def inMetersPerSecond(self):
        """
        The speed that this object represents, expressed in meters per second.
        This attribute is immutable.

        @return: The speed this object represents, in meters per second.
        @rtype: C{float}
        """
        return self._speed

    @property
    def inKnots(self):
        """
        Returns the speed represented by this object, expressed in knots. This
        attribute is immutable.

        @return: The speed this object represents, in knots.
        @rtype: C{float}
        """
        return self._speed / MPS_PER_KNOT

    def __float__(self):
        """
        Returns the speed represented by this object expressed in meters per
        second.

        @return: The speed represented by this object, expressed in meters per
            second.
        @rtype: C{float}
        """
        return self._speed

    def __repr__(self) -> str:
        """
        Returns a string representation of this speed object.

        @return: The string representation.
        @rtype: C{str}
        """
        speedValue = round(self.inMetersPerSecond, 2)
        return f"<{self.__class__.__name__} ({speedValue} m/s)>"


class Speed(_BaseSpeed):
    """
    The speed (rate of movement) of a mobile object.
    """

    def __init__(self, speed):
        """
        Initializes a L{Speed} object.

        @param speed: The speed that this object represents, expressed in
            meters per second.
        @type speed: C{float}

        @raises ValueError: Raised if C{speed} is negative.
        """
        if speed < 0:
            raise ValueError(f"negative speed: {speed!r}")

        _BaseSpeed.__init__(self, speed)


class Climb(_BaseSpeed):
    """
    The climb ("vertical speed") of an object.
    """

    def __init__(self, climb):
        """
        Initializes a L{Climb} object.

        @param climb: The climb that this object represents, expressed in
            meters per second.
        @type climb: C{float}
        """
        _BaseSpeed.__init__(self, climb)


class PositionError(FancyEqMixin):
    """
    Position error information.

    @cvar _ALLOWABLE_THRESHOLD: The maximum allowable difference between PDOP
        and the geometric mean of VDOP and HDOP. That difference is supposed
        to be zero, but can be non-zero because of rounding error and limited
        reporting precision. You should never have to change this value.
    @type _ALLOWABLE_THRESHOLD: C{float}
    @cvar _DOP_EXPRESSIONS: A mapping of DOP types (C[hvp]dop) to a list of
        callables that take self and return that DOP type, or raise
        C{TypeError}. This allows a DOP value to either be returned directly
        if it's know, or computed from other DOP types if it isn't.
    @type _DOP_EXPRESSIONS: C{dict} of C{str} to callables
    @ivar pdop: The position dilution of precision. L{None} if unknown.
    @type pdop: C{float} or L{None}
    @ivar hdop: The horizontal dilution of precision. L{None} if unknown.
    @type hdop: C{float} or L{None}
    @ivar vdop: The vertical dilution of precision. L{None} if unknown.
    @type vdop: C{float} or L{None}
    """

    compareAttributes = "pdop", "hdop", "vdop"

    def __init__(self, pdop=None, hdop=None, vdop=None, testInvariant=False):
        """
        Initializes a positioning error object.

        @param pdop: The position dilution of precision. L{None} if unknown.
        @type pdop: C{float} or L{None}
        @param hdop: The horizontal dilution of precision. L{None} if unknown.
        @type hdop: C{float} or L{None}
        @param vdop: The vertical dilution of precision. L{None} if unknown.
        @type vdop: C{float} or L{None}
        @param testInvariant: Flag to test if the DOP invariant is valid or
            not. If C{True}, the invariant (PDOP = (HDOP**2 + VDOP**2)*.5) is
            checked at every mutation. By default, this is false, because the
            vast majority of DOP-providing devices ignore this invariant.
        @type testInvariant: c{bool}
        """
        self._pdop = pdop
        self._hdop = hdop
        self._vdop = vdop

        self._testInvariant = testInvariant
        self._testDilutionOfPositionInvariant()

    _ALLOWABLE_TRESHOLD = 0.01

    def _testDilutionOfPositionInvariant(self):
        """
        Tests if this positioning error object satisfies the dilution of
        position invariant (PDOP = (HDOP**2 + VDOP**2)*.5), unless the
        C{self._testInvariant} instance variable is C{False}.

        @return: L{None} if the invariant was not satisfied or not tested.
        @raises ValueError: Raised if the invariant was tested but not
            satisfied.
        """
        if not self._testInvariant:
            return

        for x in (self.pdop, self.hdop, self.vdop):
            if x is None:
                return

        delta = abs(self.pdop - (self.hdop ** 2 + self.vdop ** 2) ** 0.5)
        if delta > self._ALLOWABLE_TRESHOLD:
            raise ValueError(
                "invalid combination of dilutions of precision: "
                "position: %s, horizontal: %s, vertical: %s"
                % (self.pdop, self.hdop, self.vdop)
            )

    _DOP_EXPRESSIONS = {
        "pdop": [
            lambda self: float(self._pdop),
            lambda self: (self._hdop ** 2 + self._vdop ** 2) ** 0.5,
        ],
        "hdop": [
            lambda self: float(self._hdop),
            lambda self: (self._pdop ** 2 - self._vdop ** 2) ** 0.5,
        ],
        "vdop": [
            lambda self: float(self._vdop),
            lambda self: (self._pdop ** 2 - self._hdop ** 2) ** 0.5,
        ],
    }

    def _getDOP(self, dopType):
        """
        Gets a particular dilution of position value.

        @param dopType: The type of dilution of position to get. One of
            ('pdop', 'hdop', 'vdop').
        @type dopType: C{str}
        @return: The DOP if it is known, L{None} otherwise.
        @rtype: C{float} or L{None}
        """
        for dopExpression in self._DOP_EXPRESSIONS[dopType]:
            try:
                return dopExpression(self)
            except TypeError:
                continue

    def _setDOP(self, dopType, value):
        """
        Sets a particular dilution of position value.

        @param dopType: The type of dilution of position to set. One of
            ('pdop', 'hdop', 'vdop').
        @type dopType: C{str}

        @param value: The value to set the dilution of position type to.
        @type value: C{float}

        If this position error tests dilution of precision invariants,
        it will be checked. If the invariant is not satisfied, the
        assignment will be undone and C{ValueError} is raised.
        """
        attributeName = "_" + dopType

        oldValue = getattr(self, attributeName)
        setattr(self, attributeName, float(value))

        try:
            self._testDilutionOfPositionInvariant()
        except ValueError:
            setattr(self, attributeName, oldValue)
            raise

    @property
    def pdop(self):
        return self._getDOP("pdop")

    @pdop.setter
    def pdop(self, value):
        return self._setDOP("pdop", value)

    @property
    def hdop(self):
        return self._getDOP("hdop")

    @hdop.setter
    def hdop(self, value):
        return self._setDOP("hdop", value)

    @property
    def vdop(self):
        return self._getDOP("vdop")

    @vdop.setter
    def vdop(self, value):
        return self._setDOP("vdop", value)

    _REPR_TEMPLATE = "<PositionError (pdop: %s, hdop: %s, vdop: %s)>"

    def __repr__(self) -> str:
        """
        Returns a string representation of positioning information object.

        @return: The string representation.
        @rtype: C{str}
        """
        return self._REPR_TEMPLATE % (self.pdop, self.hdop, self.vdop)


class BeaconInformation:
    """
    Information about positioning beacons (a generalized term for the reference
    objects that help you determine your position, such as satellites or cell
    towers).

    @ivar seenBeacons: A set of visible beacons. Note that visible beacons are not
        necessarily used in acquiring a positioning fix.
    @type seenBeacons: C{set} of L{IPositioningBeacon}
    @ivar usedBeacons: A set of the beacons that were used in obtaining a
        positioning fix. This only contains beacons that are actually used, not
        beacons for which it is unknown if they are used or not.
    @type usedBeacons: C{set} of L{IPositioningBeacon}
    """

    def __init__(self, seenBeacons=()):
        """
        Initializes a beacon information object.

        @param seenBeacons: A collection of beacons that are currently seen.
        @type seenBeacons: iterable of L{IPositioningBeacon}s
        """
        self.seenBeacons = set(seenBeacons)
        self.usedBeacons = set()

    def __repr__(self) -> str:
        """
        Returns a string representation of this beacon information object.

        The beacons are sorted by their identifier.

        @return: The string representation.
        @rtype: C{str}
        """
        sortedBeacons = partial(sorted, key=attrgetter("identifier"))

        usedBeacons = sortedBeacons(self.usedBeacons)
        unusedBeacons = sortedBeacons(self.seenBeacons - self.usedBeacons)

        template = (
            "<BeaconInformation ("
            "used beacons ({numUsed}): {usedBeacons}, "
            "unused beacons: {unusedBeacons})>"
        )

        formatted = template.format(
            numUsed=len(self.usedBeacons),
            usedBeacons=usedBeacons,
            unusedBeacons=unusedBeacons,
        )

        return formatted


@implementer(ipositioning.IPositioningBeacon)
class PositioningBeacon:
    """
    A positioning beacon.

    @ivar identifier: The unique identifier for this beacon. This is usually
        an integer. For GPS, this is also known as the PRN.
    @type identifier: Pretty much anything that can be used as a unique
        identifier. Depends on the implementation.
    """

    def __init__(self, identifier):
        """
        Initializes a positioning beacon.

        @param identifier: The identifier for this beacon.
        @type identifier: Can be pretty much anything (see ivar documentation).
        """
        self.identifier = identifier

    def __hash__(self):
        """
        Returns the hash of the identifier for this beacon.

        @return: The hash of the identifier. (C{hash(self.identifier)})
        @rtype: C{int}
        """
        return hash(self.identifier)

    def __repr__(self) -> str:
        """
        Returns a string representation of this beacon.

        @return: The string representation.
        @rtype: C{str}
        """
        return f"<Beacon ({self.identifier})>"


class Satellite(PositioningBeacon):
    """
    A satellite.

    @ivar azimuth: The azimuth of the satellite. This is the heading (positive
        angle relative to true north) where the satellite appears to be to the
        device.
    @ivar elevation: The (positive) angle above the horizon where this
        satellite appears to be to the device.
    @ivar signalToNoiseRatio: The signal to noise ratio of the signal coming
        from this satellite.
    """

    def __init__(
        self, identifier, azimuth=None, elevation=None, signalToNoiseRatio=None
    ):
        """
        Initializes a satellite object.

        @param identifier: The PRN (unique identifier) of this satellite.
        @type identifier: C{int}
        @param azimuth: The azimuth of the satellite (see instance variable
            documentation).
        @type azimuth: C{float}
        @param elevation: The elevation of the satellite (see instance variable
            documentation).
        @type elevation: C{float}
        @param signalToNoiseRatio: The signal to noise ratio of the connection
            to this satellite (see instance variable documentation).
        @type signalToNoiseRatio: C{float}
        """
        PositioningBeacon.__init__(self, int(identifier))

        self.azimuth = azimuth
        self.elevation = elevation
        self.signalToNoiseRatio = signalToNoiseRatio

    def __repr__(self) -> str:
        """
        Returns a string representation of this Satellite.

        @return: The string representation.
        @rtype: C{str}
        """
        template = (
            "<Satellite ({s.identifier}), "
            "azimuth: {s.azimuth}, "
            "elevation: {s.elevation}, "
            "snr: {s.signalToNoiseRatio}>"
        )

        return template.format(s=self)


__all__ = [
    "Altitude",
    "Angle",
    "Angles",
    "BasePositioningReceiver",
    "BeaconInformation",
    "Climb",
    "Coordinate",
    "Directions",
    "Heading",
    "InvalidChecksum",
    "InvalidSentence",
    "METERS_PER_FOOT",
    "MPS_PER_KNOT",
    "MPS_PER_KPH",
    "PositionError",
    "PositioningBeacon",
    "Satellite",
    "Speed",
]

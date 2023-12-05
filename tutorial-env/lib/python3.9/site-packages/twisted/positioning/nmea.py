# -*- test-case-name: twisted.positioning.test.test_nmea -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
"""
Classes for working with NMEA 0183 sentence producing devices.
This standard is generally just called "NMEA", which is actually the
name of the body that produces the standard, not the standard itself..

For more information, read the blog post on NMEA by ESR (the gpsd
maintainer) at U{http://esr.ibiblio.org/?p=801}. Unfortunately,
official specifications on NMEA 0183 are only available at a cost.

More information can be found on the Wikipedia page:
U{https://en.wikipedia.org/wiki/NMEA_0183}.

The official standard may be obtained through the NMEA's website:
U{http://www.nmea.org/content/nmea_standards/nmea_0183_v_410.asp}.

@since: 14.0
"""


import datetime
import operator
from functools import reduce

from zope.interface import implementer

from constantly import ValueConstant, Values  # type: ignore[import]

from twisted.positioning import _sentence, base, ipositioning
from twisted.positioning.base import Angles
from twisted.protocols.basic import LineReceiver
from twisted.python.compat import iterbytes, nativeString


class GPGGAFixQualities(Values):
    """
    The possible fix quality indications for GPGGA sentences.

    @cvar INVALID_FIX: The fix is invalid.
    @cvar GPS_FIX: There is a fix, acquired using GPS.
    @cvar DGPS_FIX: There is a fix, acquired using differential GPS (DGPS).
    @cvar PPS_FIX: There is a fix, acquired using the precise positioning
        service (PPS).
    @cvar RTK_FIX: There is a fix, acquired using fixed real-time
        kinematics. This means that there was a sufficient number of shared
        satellites with the base station, usually yielding a resolution in
        the centimeter range. This was added in NMEA 0183 version 3.0. This
        is also called Carrier-Phase Enhancement or CPGPS, particularly when
        used in combination with GPS.
    @cvar FLOAT_RTK_FIX: There is a fix, acquired using floating real-time
        kinematics. The same comments apply as for a fixed real-time
        kinematics fix, except that there were insufficient shared satellites
        to acquire it, so instead you got a slightly less good floating fix.
        Typical resolution in the decimeter range.
    @cvar DEAD_RECKONING: There is currently no more fix, but this data was
        computed using a previous fix and some information about motion
        (either from that fix or from other sources) using simple dead
        reckoning. Not particularly reliable, but better-than-nonsense data.
    @cvar MANUAL: There is no real fix from this device, but the location has
        been manually entered, presumably with data obtained from some other
        positioning method.
    @cvar SIMULATED: There is no real fix, but instead it is being simulated.
    """

    INVALID_FIX = "0"
    GPS_FIX = "1"
    DGPS_FIX = "2"
    PPS_FIX = "3"
    RTK_FIX = "4"
    FLOAT_RTK_FIX = "5"
    DEAD_RECKONING = "6"
    MANUAL = "7"
    SIMULATED = "8"


class GPGLLGPRMCFixQualities(Values):
    """
    The possible fix quality indications in GPGLL and GPRMC sentences.

    Unfortunately, these sentences only indicate whether data is good or void.
    They provide no other information, such as what went wrong if the data is
    void, or how good the data is if the data is not void.

    @cvar ACTIVE: The data is okay.
    @cvar VOID: The data is void, and should not be used.
    """

    ACTIVE = ValueConstant("A")
    VOID = ValueConstant("V")


class GPGSAFixTypes(Values):
    """
    The possible fix types of a GPGSA sentence.

    @cvar GSA_NO_FIX: The sentence reports no fix at all.
    @cvar GSA_2D_FIX: The sentence reports a 2D fix: position but no altitude.
    @cvar GSA_3D_FIX: The sentence reports a 3D fix: position with altitude.
    """

    GSA_NO_FIX = ValueConstant("1")
    GSA_2D_FIX = ValueConstant("2")
    GSA_3D_FIX = ValueConstant("3")


def _split(sentence):
    """
    Returns the split version of an NMEA sentence, minus header
    and checksum.

    >>> _split(b"$GPGGA,spam,eggs*00")
    [b'GPGGA', b'spam', b'eggs']

    @param sentence: The NMEA sentence to split.
    @type sentence: C{bytes}
    """
    if sentence[-3:-2] == b"*":  # Sentence with checksum
        return sentence[1:-3].split(b",")
    elif sentence[-1:] == b"*":  # Sentence without checksum
        return sentence[1:-1].split(b",")
    else:
        raise base.InvalidSentence(f"malformed sentence {sentence}")


def _validateChecksum(sentence):
    """
    Validates the checksum of an NMEA sentence.

    @param sentence: The NMEA sentence to check the checksum of.
    @type sentence: C{bytes}

    @raise ValueError: If the sentence has an invalid checksum.

    Simply returns on sentences that either don't have a checksum,
    or have a valid checksum.
    """
    if sentence[-3:-2] == b"*":  # Sentence has a checksum
        reference, source = int(sentence[-2:], 16), sentence[1:-3]
        computed = reduce(operator.xor, [ord(x) for x in iterbytes(source)])
        if computed != reference:
            raise base.InvalidChecksum(f"{computed:02x} != {reference:02x}")


class NMEAProtocol(LineReceiver, _sentence._PositioningSentenceProducerMixin):
    """
    A protocol that parses and verifies the checksum of an NMEA sentence (in
    string form, not L{NMEASentence}), and delegates to a receiver.

    It receives lines and verifies these lines are NMEA sentences. If
    they are, verifies their checksum and unpacks them into their
    components. It then wraps them in L{NMEASentence} objects and
    calls the appropriate receiver method with them.

    @cvar _SENTENCE_CONTENTS: Has the field names in an NMEA sentence for each
        sentence type (in order, obviously).
    @type _SENTENCE_CONTENTS: C{dict} of bytestrings to C{list}s of C{str}
    @param receiver: A receiver for NMEAProtocol sentence objects.
    @type receiver: L{INMEAReceiver}
    @param sentenceCallback: A function that will be called with a new
        L{NMEASentence} when it is created. Useful for massaging data from
        particularly misbehaving NMEA receivers.
    @type sentenceCallback: unary callable
    """

    def __init__(self, receiver, sentenceCallback=None):
        """
        Initializes an NMEAProtocol.

        @param receiver: A receiver for NMEAProtocol sentence objects.
        @type receiver: L{INMEAReceiver}
        @param sentenceCallback: A function that will be called with a new
            L{NMEASentence} when it is created. Useful for massaging data from
            particularly misbehaving NMEA receivers.
        @type sentenceCallback: unary callable
        """
        self._receiver = receiver
        self._sentenceCallback = sentenceCallback

    def lineReceived(self, rawSentence):
        """
        Parses the data from the sentence and validates the checksum.

        @param rawSentence: The NMEA positioning sentence.
        @type rawSentence: C{bytes}
        """
        sentence = rawSentence.strip()

        _validateChecksum(sentence)
        splitSentence = _split(sentence)

        sentenceType = nativeString(splitSentence[0])
        contents = [nativeString(x) for x in splitSentence[1:]]

        try:
            keys = self._SENTENCE_CONTENTS[sentenceType]
        except KeyError:
            raise ValueError("unknown sentence type %s" % sentenceType)

        sentenceData = {"type": sentenceType}
        for key, value in zip(keys, contents):
            if key is not None and value != "":
                sentenceData[key] = value

        sentence = NMEASentence(sentenceData)

        if self._sentenceCallback is not None:
            self._sentenceCallback(sentence)

        self._receiver.sentenceReceived(sentence)

    _SENTENCE_CONTENTS = {
        "GPGGA": [
            "timestamp",
            "latitudeFloat",
            "latitudeHemisphere",
            "longitudeFloat",
            "longitudeHemisphere",
            "fixQuality",
            "numberOfSatellitesSeen",
            "horizontalDilutionOfPrecision",
            "altitude",
            "altitudeUnits",
            "heightOfGeoidAboveWGS84",
            "heightOfGeoidAboveWGS84Units",
            # The next parts are DGPS information, currently unused.
            None,  # Time since last DGPS update
            None,  # DGPS reference source id
        ],
        "GPRMC": [
            "timestamp",
            "dataMode",
            "latitudeFloat",
            "latitudeHemisphere",
            "longitudeFloat",
            "longitudeHemisphere",
            "speedInKnots",
            "trueHeading",
            "datestamp",
            "magneticVariation",
            "magneticVariationDirection",
        ],
        "GPGSV": [
            "numberOfGSVSentences",
            "GSVSentenceIndex",
            "numberOfSatellitesSeen",
            "satellitePRN_0",
            "elevation_0",
            "azimuth_0",
            "signalToNoiseRatio_0",
            "satellitePRN_1",
            "elevation_1",
            "azimuth_1",
            "signalToNoiseRatio_1",
            "satellitePRN_2",
            "elevation_2",
            "azimuth_2",
            "signalToNoiseRatio_2",
            "satellitePRN_3",
            "elevation_3",
            "azimuth_3",
            "signalToNoiseRatio_3",
        ],
        "GPGLL": [
            "latitudeFloat",
            "latitudeHemisphere",
            "longitudeFloat",
            "longitudeHemisphere",
            "timestamp",
            "dataMode",
        ],
        "GPHDT": [
            "trueHeading",
        ],
        "GPTRF": [
            "datestamp",
            "timestamp",
            "latitudeFloat",
            "latitudeHemisphere",
            "longitudeFloat",
            "longitudeHemisphere",
            "elevation",
            "numberOfIterations",  # Unused
            "numberOfDopplerIntervals",  # Unused
            "updateDistanceInNauticalMiles",  # Unused
            "satellitePRN",
        ],
        "GPGSA": [
            "dataMode",
            "fixType",
            "usedSatellitePRN_0",
            "usedSatellitePRN_1",
            "usedSatellitePRN_2",
            "usedSatellitePRN_3",
            "usedSatellitePRN_4",
            "usedSatellitePRN_5",
            "usedSatellitePRN_6",
            "usedSatellitePRN_7",
            "usedSatellitePRN_8",
            "usedSatellitePRN_9",
            "usedSatellitePRN_10",
            "usedSatellitePRN_11",
            "positionDilutionOfPrecision",
            "horizontalDilutionOfPrecision",
            "verticalDilutionOfPrecision",
        ],
    }


class NMEASentence(_sentence._BaseSentence):
    """
    An object representing an NMEA sentence.

    The attributes of this objects are raw NMEA protocol data, which
    are all ASCII bytestrings.

    This object contains all the raw NMEA protocol data in a single
    sentence.  Not all of these necessarily have to be present in the
    sentence. Missing attributes are L{None} when accessed.

    @ivar type: The sentence type (C{"GPGGA"}, C{"GPGSV"}...).
    @ivar numberOfGSVSentences: The total number of GSV sentences in a
        sequence.
    @ivar GSVSentenceIndex: The index of this GSV sentence in the GSV
        sequence.
    @ivar timestamp: A timestamp. (C{"123456"} -> 12:34:56Z)
    @ivar datestamp: A datestamp. (C{"230394"} -> 23 Mar 1994)
    @ivar latitudeFloat: Latitude value. (for example: C{"1234.567"} ->
        12 degrees, 34.567 minutes).
    @ivar latitudeHemisphere: Latitudinal hemisphere (C{"N"} or C{"S"}).
    @ivar longitudeFloat: Longitude value. See C{latitudeFloat} for an
        example.
    @ivar longitudeHemisphere: Longitudinal hemisphere (C{"E"} or C{"W"}).
    @ivar altitude: The altitude above mean sea level.
    @ivar altitudeUnits: Units in which altitude is expressed. (Always
        C{"M"} for meters.)
    @ivar heightOfGeoidAboveWGS84: The local height of the geoid above
        the WGS84 ellipsoid model.
    @ivar heightOfGeoidAboveWGS84Units: The units in which the height
        above the geoid is expressed. (Always C{"M"} for meters.)
    @ivar trueHeading: The true heading.
    @ivar magneticVariation: The magnetic variation.
    @ivar magneticVariationDirection: The direction of the magnetic
        variation. One of C{"E"} or C{"W"}.
    @ivar speedInKnots: The ground speed, expressed in knots.
    @ivar fixQuality: The quality of the fix.
    @type fixQuality: One of L{GPGGAFixQualities}.
    @ivar dataMode: Signals if the data is usable or not.
    @type dataMode: One of L{GPGLLGPRMCFixQualities}.
    @ivar numberOfSatellitesSeen: The number of satellites seen by the
        receiver.
    @ivar numberOfSatellitesUsed: The number of satellites used in
        computing the fix.
    @ivar horizontalDilutionOfPrecision: The dilution of the precision of the
        position on a plane tangential to the geoid. (HDOP)
    @ivar verticalDilutionOfPrecision: As C{horizontalDilutionOfPrecision},
        but for a position on a plane perpendicular to the geoid. (VDOP)
    @ivar positionDilutionOfPrecision: Euclidean norm of HDOP and VDOP.
    @ivar satellitePRN: The unique identifcation number of a particular
        satellite. Optionally suffixed with C{_N} if multiple satellites are
        referenced in a sentence, where C{N in range(4)}.
    @ivar elevation: The elevation of a satellite in decimal degrees.
        Optionally suffixed with C{_N}, as with C{satellitePRN}.
    @ivar azimuth: The azimuth of a satellite in decimal degrees.
        Optionally suffixed with C{_N}, as with C{satellitePRN}.
    @ivar signalToNoiseRatio: The SNR of a satellite signal, in decibels.
        Optionally suffixed with C{_N}, as with C{satellitePRN}.
    @ivar usedSatellitePRN_N: Where C{int(N) in range(12)}. The PRN
        of a satellite used in computing the fix.
    """

    ALLOWED_ATTRIBUTES = NMEAProtocol.getSentenceAttributes()

    def _isFirstGSVSentence(self):
        """
        Tests if this current GSV sentence is the first one in a sequence.

        @return: C{True} if this is the first GSV sentence.
        @rtype: C{bool}
        """
        return self.GSVSentenceIndex == "1"

    def _isLastGSVSentence(self):
        """
        Tests if this current GSV sentence is the final one in a sequence.

        @return: C{True} if this is the last GSV sentence.
        @rtype: C{bool}
        """
        return self.GSVSentenceIndex == self.numberOfGSVSentences


@implementer(ipositioning.INMEAReceiver)
class NMEAAdapter:
    """
    An adapter from NMEAProtocol receivers to positioning receivers.

    @cvar _STATEFUL_UPDATE: Information on how to update partial information
        in the sentence data or internal adapter state. For more information,
        see C{_statefulUpdate}'s docstring.
    @type _STATEFUL_UPDATE: See C{_statefulUpdate}'s docstring
    @cvar _ACCEPTABLE_UNITS: A set of NMEA notations of units that are
        already acceptable (metric), and therefore don't need to be converted.
    @type _ACCEPTABLE_UNITS: C{frozenset} of bytestrings
    @cvar _UNIT_CONVERTERS: Mapping of NMEA notations of units that are not
        acceptable (not metric) to converters that take a quantity in that
        unit and produce a metric quantity.
    @type _UNIT_CONVERTERS: C{dict} of bytestrings to unary callables
    @cvar  _SPECIFIC_SENTENCE_FIXES: A mapping of sentece types to specific
        fixes that are required to extract useful information from data from
        those sentences.
    @type  _SPECIFIC_SENTENCE_FIXES: C{dict} of sentence types to callables
        that take self and modify it in-place
    @cvar _FIXERS: Set of unary callables that take an NMEAAdapter instance
        and extract useful data from the sentence data, usually modifying the
        adapter's sentence data in-place.
    @type _FIXERS: C{dict} of native strings to unary callables
    @ivar yearThreshold: The earliest possible year that data will be
        interpreted as. For example, if this value is C{1990}, an NMEA
        0183 two-digit year of "96" will be interpreted as 1996, and
        a two-digit year of "13" will be interpreted as 2013.
    @type yearThreshold: L{int}
    @ivar _state: The current internal state of the receiver.
    @type _state: C{dict}
    @ivar _sentenceData: The data present in the sentence currently being
        processed. Starts empty, is filled as the sentence is parsed.
    @type _sentenceData: C{dict}
    @ivar _receiver: The positioning receiver that will receive parsed data.
    @type _receiver: L{ipositioning.IPositioningReceiver}
    """

    def __init__(self, receiver):
        """
        Initializes a new NMEA adapter.

        @param receiver: The receiver for positioning sentences.
        @type receiver: L{ipositioning.IPositioningReceiver}
        """
        self._state = {}
        self._sentenceData = {}
        self._receiver = receiver

    def _fixTimestamp(self):
        """
        Turns the NMEAProtocol timestamp notation into a datetime.time object.
        The time in this object is expressed as Zulu time.
        """
        timestamp = self.currentSentence.timestamp.split(".")[0]
        timeObject = datetime.datetime.strptime(timestamp, "%H%M%S").time()
        self._sentenceData["_time"] = timeObject

    yearThreshold = 1980

    def _fixDatestamp(self):
        """
        Turns an NMEA datestamp format into a C{datetime.date} object.

        @raise ValueError: When the day or month value was invalid, e.g. 32nd
            day, or 13th month, or 0th day or month.
        """
        date = self.currentSentence.datestamp
        day, month, year = map(int, [date[0:2], date[2:4], date[4:6]])

        year += self.yearThreshold - (self.yearThreshold % 100)
        if year < self.yearThreshold:
            year += 100

        self._sentenceData["_date"] = datetime.date(year, month, day)

    def _fixCoordinateFloat(self, coordinateType):
        """
        Turns the NMEAProtocol coordinate format into Python float.

        @param coordinateType: The coordinate type.
        @type coordinateType: One of L{Angles.LATITUDE} or L{Angles.LONGITUDE}.
        """
        if coordinateType is Angles.LATITUDE:
            coordinateName = "latitude"
        else:  # coordinateType is Angles.LONGITUDE
            coordinateName = "longitude"
        nmeaCoordinate = getattr(self.currentSentence, coordinateName + "Float")

        left, right = nmeaCoordinate.split(".")

        degrees, minutes = int(left[:-2]), float(f"{left[-2:]}.{right}")
        angle = degrees + minutes / 60
        coordinate = base.Coordinate(angle, coordinateType)
        self._sentenceData[coordinateName] = coordinate

    def _fixHemisphereSign(self, coordinateType, sentenceDataKey=None):
        """
        Fixes the sign for a hemisphere.

        This method must be called after the magnitude for the thing it
        determines the sign of has been set. This is done by the following
        functions:

            - C{self.FIXERS['magneticVariation']}
            - C{self.FIXERS['latitudeFloat']}
            - C{self.FIXERS['longitudeFloat']}

        @param coordinateType: Coordinate type. One of L{Angles.LATITUDE},
            L{Angles.LONGITUDE} or L{Angles.VARIATION}.
        @param sentenceDataKey: The key name of the hemisphere sign being
            fixed in the sentence data. If unspecified, C{coordinateType} is
            used.
        @type sentenceDataKey: C{str} (unless L{None})
        """
        sentenceDataKey = sentenceDataKey or coordinateType
        sign = self._getHemisphereSign(coordinateType)
        self._sentenceData[sentenceDataKey].setSign(sign)

    def _getHemisphereSign(self, coordinateType):
        """
        Returns the hemisphere sign for a given coordinate type.

        @param coordinateType: The coordinate type to find the hemisphere for.
        @type coordinateType: L{Angles.LATITUDE}, L{Angles.LONGITUDE} or
            L{Angles.VARIATION}.
        @return: The sign of that hemisphere (-1 or 1).
        @rtype: C{int}
        """
        if coordinateType is Angles.LATITUDE:
            hemisphereKey = "latitudeHemisphere"
        elif coordinateType is Angles.LONGITUDE:
            hemisphereKey = "longitudeHemisphere"
        elif coordinateType is Angles.VARIATION:
            hemisphereKey = "magneticVariationDirection"
        else:
            raise ValueError(f"unknown coordinate type {coordinateType}")

        hemisphere = getattr(self.currentSentence, hemisphereKey).upper()

        if hemisphere in "NE":
            return 1
        elif hemisphere in "SW":
            return -1
        else:
            raise ValueError(f"bad hemisphere/direction: {hemisphere}")

    def _convert(self, key, converter):
        """
        A simple conversion fix.

        @param key: The attribute name of the value to fix.
        @type key: native string (Python identifier)

        @param converter: The function that converts the value.
        @type converter: unary callable
        """
        currentValue = getattr(self.currentSentence, key)
        self._sentenceData[key] = converter(currentValue)

    _STATEFUL_UPDATE = {
        # sentenceKey: (stateKey, factory, attributeName, converter),
        "trueHeading": ("heading", base.Heading, "_angle", float),
        "magneticVariation": (
            "heading",
            base.Heading,
            "variation",
            lambda angle: base.Angle(float(angle), Angles.VARIATION),
        ),
        "horizontalDilutionOfPrecision": (
            "positionError",
            base.PositionError,
            "hdop",
            float,
        ),
        "verticalDilutionOfPrecision": (
            "positionError",
            base.PositionError,
            "vdop",
            float,
        ),
        "positionDilutionOfPrecision": (
            "positionError",
            base.PositionError,
            "pdop",
            float,
        ),
    }

    def _statefulUpdate(self, sentenceKey):
        """
        Does a stateful update of a particular positioning attribute.
        Specifically, this will mutate an object in the current sentence data.

        Using the C{sentenceKey}, this will get a tuple containing, in order,
        the key name in the current state and sentence data, a factory for
        new values, the attribute to update, and a converter from sentence
        data (in NMEA notation) to something useful.

        If the sentence data doesn't have this data yet, it is grabbed from
        the state. If that doesn't have anything useful yet either, the
        factory is called to produce a new, empty object. Either way, the
        object ends up in the sentence data.

        @param sentenceKey: The name of the key in the sentence attributes,
            C{NMEAAdapter._STATEFUL_UPDATE} dictionary and the adapter state.
        @type sentenceKey: C{str}
        """
        key, factory, attr, converter = self._STATEFUL_UPDATE[sentenceKey]

        if key not in self._sentenceData:
            try:
                self._sentenceData[key] = self._state[key]
            except KeyError:  # state does not have this partial data yet
                self._sentenceData[key] = factory()

        newValue = converter(getattr(self.currentSentence, sentenceKey))
        setattr(self._sentenceData[key], attr, newValue)

    _ACCEPTABLE_UNITS = frozenset(["M"])
    _UNIT_CONVERTERS = {
        "N": lambda inKnots: base.Speed(float(inKnots) * base.MPS_PER_KNOT),
        "K": lambda inKPH: base.Speed(float(inKPH) * base.MPS_PER_KPH),
    }

    def _fixUnits(self, unitKey=None, valueKey=None, sourceKey=None, unit=None):
        """
        Fixes the units of a certain value. If the units are already
        acceptable (metric), does nothing.

        None of the keys are allowed to be the empty string.

        @param unit: The unit that is being converted I{from}. If unspecified
            or L{None}, asks the current sentence for the C{unitKey}. If that
            also fails, raises C{AttributeError}.
        @type unit: C{str}
        @param unitKey: The name of the key/attribute under which the unit can
            be found in the current sentence. If the C{unit} parameter is set,
            this parameter is not used.
        @type unitKey: C{str}
        @param sourceKey: The name of the key/attribute that contains the
            current value to be converted (expressed in units as defined
            according to the C{unit} parameter). If unset, will use the
            same key as the value key.
        @type sourceKey: C{str}
        @param valueKey: The key name in which the data will be stored in the
            C{_sentenceData} instance attribute. If unset, attempts to remove
            "Units" from the end of the C{unitKey} parameter. If that fails,
            raises C{ValueError}.
        @type valueKey: C{str}
        """
        if unit is None:
            unit = getattr(self.currentSentence, unitKey)
        if valueKey is None:
            if unitKey is not None and unitKey.endswith("Units"):
                valueKey = unitKey[:-5]
            else:
                raise ValueError("valueKey unspecified and couldn't be guessed")
        if sourceKey is None:
            sourceKey = valueKey

        if unit not in self._ACCEPTABLE_UNITS:
            converter = self._UNIT_CONVERTERS[unit]
            currentValue = getattr(self.currentSentence, sourceKey)
            self._sentenceData[valueKey] = converter(currentValue)

    def _fixGSV(self):
        """
        Parses partial visible satellite information from a GSV sentence.
        """
        # To anyone who knows NMEA, this method's name should raise a chuckle's
        # worth of schadenfreude. 'Fix' GSV? Hah! Ludicrous.
        beaconInformation = base.BeaconInformation()
        self._sentenceData["_partialBeaconInformation"] = beaconInformation

        keys = "satellitePRN", "azimuth", "elevation", "signalToNoiseRatio"
        for index in range(4):
            prn, azimuth, elevation, snr = (
                getattr(self.currentSentence, attr)
                for attr in ("%s_%i" % (key, index) for key in keys)
            )

            if prn is None or snr is None:
                # The peephole optimizer optimizes the jump away, meaning that
                # coverage.py thinks it isn't covered. It is. Replace it with
                # break, and watch the test case fail.
                # ML thread about this issue: http://goo.gl/1KNUi
                # Related CPython bug: http://bugs.python.org/issue2506
                continue

            satellite = base.Satellite(prn, azimuth, elevation, snr)
            beaconInformation.seenBeacons.add(satellite)

    def _fixGSA(self):
        """
        Extracts the information regarding which satellites were used in
        obtaining the GPS fix from a GSA sentence.

        Precondition: A GSA sentence was fired. Postcondition: The current
        sentence data (C{self._sentenceData} will contain a set of the
        currently used PRNs (under the key C{_usedPRNs}.
        """
        self._sentenceData["_usedPRNs"] = set()
        for key in ("usedSatellitePRN_%d" % (x,) for x in range(12)):
            prn = getattr(self.currentSentence, key, None)
            if prn is not None:
                self._sentenceData["_usedPRNs"].add(int(prn))

    _SPECIFIC_SENTENCE_FIXES = {
        "GPGSV": _fixGSV,
        "GPGSA": _fixGSA,
    }

    def _sentenceSpecificFix(self):
        """
        Executes a fix for a specific type of sentence.
        """
        fixer = self._SPECIFIC_SENTENCE_FIXES.get(self.currentSentence.type)
        if fixer is not None:
            fixer(self)

    _FIXERS = {
        "type": lambda self: self._sentenceSpecificFix(),
        "timestamp": lambda self: self._fixTimestamp(),
        "datestamp": lambda self: self._fixDatestamp(),
        "latitudeFloat": lambda self: self._fixCoordinateFloat(Angles.LATITUDE),
        "latitudeHemisphere": lambda self: self._fixHemisphereSign(
            Angles.LATITUDE, "latitude"
        ),
        "longitudeFloat": lambda self: self._fixCoordinateFloat(Angles.LONGITUDE),
        "longitudeHemisphere": lambda self: self._fixHemisphereSign(
            Angles.LONGITUDE, "longitude"
        ),
        "altitude": lambda self: self._convert(
            "altitude", converter=lambda strRepr: base.Altitude(float(strRepr))
        ),
        "altitudeUnits": lambda self: self._fixUnits(unitKey="altitudeUnits"),
        "heightOfGeoidAboveWGS84": lambda self: self._convert(
            "heightOfGeoidAboveWGS84",
            converter=lambda strRepr: base.Altitude(float(strRepr)),
        ),
        "heightOfGeoidAboveWGS84Units": lambda self: self._fixUnits(
            unitKey="heightOfGeoidAboveWGS84Units"
        ),
        "trueHeading": lambda self: self._statefulUpdate("trueHeading"),
        "magneticVariation": lambda self: self._statefulUpdate("magneticVariation"),
        "magneticVariationDirection": lambda self: self._fixHemisphereSign(
            Angles.VARIATION, "heading"
        ),
        "speedInKnots": lambda self: self._fixUnits(
            valueKey="speed", sourceKey="speedInKnots", unit="N"
        ),
        "positionDilutionOfPrecision": lambda self: self._statefulUpdate(
            "positionDilutionOfPrecision"
        ),
        "horizontalDilutionOfPrecision": lambda self: self._statefulUpdate(
            "horizontalDilutionOfPrecision"
        ),
        "verticalDilutionOfPrecision": lambda self: self._statefulUpdate(
            "verticalDilutionOfPrecision"
        ),
    }

    def clear(self):
        """
        Resets this adapter.

        This will empty the adapter state and the current sentence data.
        """
        self._state = {}
        self._sentenceData = {}

    def sentenceReceived(self, sentence):
        """
        Called when a sentence is received.

        Will clean the received NMEAProtocol sentence up, and then update the
        adapter's state, followed by firing the callbacks.

        If the received sentence was invalid, the state will be cleared.

        @param sentence: The sentence that is received.
        @type sentence: L{NMEASentence}
        """
        self.currentSentence = sentence
        self._sentenceData = {}

        try:
            self._validateCurrentSentence()
            self._cleanCurrentSentence()
        except base.InvalidSentence:
            self.clear()

        self._updateState()
        self._fireSentenceCallbacks()

    def _validateCurrentSentence(self):
        """
        Tests if a sentence contains a valid fix.
        """
        if (
            self.currentSentence.fixQuality is GPGGAFixQualities.INVALID_FIX
            or self.currentSentence.dataMode is GPGLLGPRMCFixQualities.VOID
            or self.currentSentence.fixType is GPGSAFixTypes.GSA_NO_FIX
        ):
            raise base.InvalidSentence("bad sentence")

    def _cleanCurrentSentence(self):
        """
        Cleans the current sentence.
        """
        for key in sorted(self.currentSentence.presentAttributes):
            fixer = self._FIXERS.get(key, None)

            if fixer is not None:
                fixer(self)

    def _updateState(self):
        """
        Updates the current state with the new information from the sentence.
        """
        self._updateBeaconInformation()
        self._combineDateAndTime()
        self._state.update(self._sentenceData)

    def _updateBeaconInformation(self):
        """
        Updates existing beacon information state with new data.
        """
        new = self._sentenceData.get("_partialBeaconInformation")
        if new is None:
            return

        self._updateUsedBeacons(new)
        self._mergeBeaconInformation(new)

        if self.currentSentence._isLastGSVSentence():
            if not self.currentSentence._isFirstGSVSentence():
                # not a 1-sentence sequence, get rid of partial information
                del self._state["_partialBeaconInformation"]
            bi = self._sentenceData.pop("_partialBeaconInformation")
            self._sentenceData["beaconInformation"] = bi

    def _updateUsedBeacons(self, beaconInformation):
        """
        Searches the adapter state and sentence data for information about
        which beacons where used, then adds it to the provided beacon
        information object.

        If no new beacon usage information is available, does nothing.

        @param beaconInformation: The beacon information object that beacon
            usage information will be added to (if necessary).
        @type beaconInformation: L{twisted.positioning.base.BeaconInformation}
        """
        for source in [self._state, self._sentenceData]:
            usedPRNs = source.get("_usedPRNs")
            if usedPRNs is not None:
                break
        else:  # No used PRN info to update
            return

        for beacon in beaconInformation.seenBeacons:
            if beacon.identifier in usedPRNs:
                beaconInformation.usedBeacons.add(beacon)

    def _mergeBeaconInformation(self, newBeaconInformation):
        """
        Merges beacon information in the adapter state (if it exists) into
        the provided beacon information. Specifically, this merges used and
        seen beacons.

        If the adapter state has no beacon information, does nothing.

        @param newBeaconInformation: The beacon information object that beacon
            information will be merged into (if necessary).
        @type newBeaconInformation: L{twisted.positioning.base.BeaconInformation}
        """
        old = self._state.get("_partialBeaconInformation")
        if old is None:
            return

        for attr in ["seenBeacons", "usedBeacons"]:
            getattr(newBeaconInformation, attr).update(getattr(old, attr))

    def _combineDateAndTime(self):
        """
        Combines a C{datetime.date} object and a C{datetime.time} object,
        collected from one or more NMEA sentences, into a single
        C{datetime.datetime} object suitable for sending to the
        L{IPositioningReceiver}.
        """
        if not any(k in self._sentenceData for k in ["_date", "_time"]):
            # If the sentence has neither date nor time, there's
            # nothing new to combine here.
            return

        date, time = (
            self._sentenceData.get(key) or self._state.get(key)
            for key in ("_date", "_time")
        )

        if date is None or time is None:
            return

        dt = datetime.datetime.combine(date, time)
        self._sentenceData["time"] = dt

    def _fireSentenceCallbacks(self):
        """
        Fires sentence callbacks for the current sentence.

        A callback will only fire if all of the keys it requires are present
        in the current state and at least one such field was altered in the
        current sentence.

        The callbacks will only be fired with data from L{_state}.
        """
        iface = ipositioning.IPositioningReceiver
        for name, method in iface.namesAndDescriptions():
            callback = getattr(self._receiver, name)

            kwargs = {}
            atLeastOnePresentInSentence = False

            try:
                for field in method.positional:
                    if field in self._sentenceData:
                        atLeastOnePresentInSentence = True
                    kwargs[field] = self._state[field]
            except KeyError:
                continue

            if atLeastOnePresentInSentence:
                callback(**kwargs)


__all__ = ["NMEAProtocol", "NMEASentence", "NMEAAdapter"]

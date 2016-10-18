# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
"""
Test cases for positioning primitives.
"""
from twisted.trial.unittest import TestCase
from twisted.positioning import base
from twisted.positioning.base import Angles, Directions
from twisted.positioning.ipositioning import IPositioningBeacon
from zope.interface import verify


class AngleTests(TestCase):
    """
    Tests for the L{twisted.positioning.base.Angle} class.
    """
    def test_empty(self):
        """
        The repr of an empty angle says that is of unknown type and unknown
        value.
        """
        a = base.Angle()
        self.assertEqual("<Angle of unknown type (unknown value)>", repr(a))


    def test_variation(self):
        """
        The repr of an empty variation says that it is a variation of unknown
        value.
        """
        a = base.Angle(angleType=Angles.VARIATION)
        self.assertEqual("<Variation (unknown value)>", repr(a))


    def test_unknownType(self):
        """
        The repr of an angle of unknown type but a given value displays that
        type and value in its repr.
        """
        a = base.Angle(1.0)
        self.assertEqual("<Angle of unknown type (1.0 degrees)>", repr(a))


    def test_bogusType(self):
        """
        Trying to create an angle with a bogus type raises C{ValueError}.
        """
        self.assertRaises(ValueError, base.Angle, angleType="BOGUS")



class HeadingTests(TestCase):
    """
    Tests for the L{twisted.positioning.base.Heading} class.
    """
    def test_simple(self):
        """
        Tests that a simple heading has a value in decimal degrees, which is
        also its value when converted to a float. Its variation, and by
        consequence its corrected heading, is L{None}.
        """
        h = base.Heading(1.)
        self.assertEqual(h.inDecimalDegrees, 1.)
        self.assertEqual(float(h), 1.)
        self.assertIsNone(h.variation)
        self.assertIsNone(h.correctedHeading)


    def test_headingWithoutVariationRepr(self):
        """
        A repr of a heading with no variation reports its value and that the
        variation is unknown.
        """
        heading = base.Heading(1.)
        expectedRepr = "<Heading (1.0 degrees, unknown variation)>"
        self.assertEqual(repr(heading), expectedRepr)


    def test_headingWithVariationRepr(self):
        """
        A repr of a heading with known variation reports its value and the
        value of that variation.
        """
        angle, variation = 1.0, -10.0
        heading = base.Heading.fromFloats(angle, variationValue=variation)
        reprTemplate = '<Heading ({0} degrees, <Variation ({1} degrees)>)>'
        self.assertEqual(repr(heading), reprTemplate.format(angle, variation))


    def test_valueEquality(self):
        """
        Headings with the same values compare equal.
        """
        self.assertEqual(base.Heading(1.), base.Heading(1.))


    def test_valueInequality(self):
        """
        Headings with different values compare unequal.
        """
        self.assertNotEqual(base.Heading(1.), base.Heading(2.))


    def test_zeroHeadingEdgeCase(self):
        """
        Headings can be instantiated with a value of 0 and no variation.
        """
        base.Heading(0)


    def test_zeroHeading180DegreeVariationEdgeCase(self):
        """
        Headings can be instantiated with a value of 0 and a variation of 180
        degrees.
        """
        base.Heading(0, 180)


    def _badValueTest(self, **kw):
        """
        Helper function for verifying that bad values raise C{ValueError}.

        @param kw: The keyword arguments passed to L{base.Heading.fromFloats}.
        """
        self.assertRaises(ValueError, base.Heading.fromFloats, **kw)


    def test_badAngleValueEdgeCase(self):
        """
        Headings can not be instantiated with a value of 360 degrees.
        """
        self._badValueTest(angleValue=360.0)


    def test_badVariationEdgeCase(self):
        """
        Headings can not be instantiated with a variation of -180 degrees.
        """
        self._badValueTest(variationValue=-180.0)


    def test_negativeHeading(self):
        """
        Negative heading values raise C{ValueError}.
        """
        self._badValueTest(angleValue=-10.0)


    def test_headingTooLarge(self):
        """
        Heading values greater than C{360.0} raise C{ValueError}.
        """
        self._badValueTest(angleValue=370.0)


    def test_variationTooNegative(self):
        """
        Variation values less than C{-180.0} raise C{ValueError}.
        """
        self._badValueTest(variationValue=-190.0)


    def test_variationTooPositive(self):
        """
        Variation values greater than C{180.0} raise C{ValueError}.
        """
        self._badValueTest(variationValue=190.0)


    def test_correctedHeading(self):
        """
        A heading with a value and a variation has a corrected heading.
        """
        h = base.Heading.fromFloats(1., variationValue=-10.)
        self.assertEqual(h.correctedHeading, base.Angle(11., Angles.HEADING))


    def test_correctedHeadingOverflow(self):
        """
        A heading with a value and a variation has the appropriate corrected
        heading value, even when the variation puts it across the 360 degree
        boundary.
        """
        h = base.Heading.fromFloats(359., variationValue=-2.)
        self.assertEqual(h.correctedHeading, base.Angle(1., Angles.HEADING))


    def test_correctedHeadingOverflowEdgeCase(self):
        """
        A heading with a value and a variation has the appropriate corrected
        heading value, even when the variation puts it exactly at the 360
        degree boundary.
        """
        h = base.Heading.fromFloats(359., variationValue=-1.)
        self.assertEqual(h.correctedHeading, base.Angle(0., Angles.HEADING))


    def test_correctedHeadingUnderflow(self):
        """
        A heading with a value and a variation has the appropriate corrected
        heading value, even when the variation puts it under the 0 degree
        boundary.
        """
        h = base.Heading.fromFloats(1., variationValue=2.)
        self.assertEqual(h.correctedHeading, base.Angle(359., Angles.HEADING))


    def test_correctedHeadingUnderflowEdgeCase(self):
        """
        A heading with a value and a variation has the appropriate corrected
        heading value, even when the variation puts it exactly at the 0
        degree boundary.
        """
        h = base.Heading.fromFloats(1., variationValue=1.)
        self.assertEqual(h.correctedHeading, base.Angle(0., Angles.HEADING))


    def test_setVariationSign(self):
        """
        Setting the sign of a heading changes the variation sign.
        """
        h = base.Heading.fromFloats(1., variationValue=1.)
        h.setSign(1)
        self.assertEqual(h.variation.inDecimalDegrees, 1.)
        h.setSign(-1)
        self.assertEqual(h.variation.inDecimalDegrees, -1.)


    def test_setBadVariationSign(self):
        """
        Setting the sign of a heading to values that aren't C{-1} or C{1}
        raises C{ValueError} and does not affect the heading.
        """
        h = base.Heading.fromFloats(1., variationValue=1.)
        self.assertRaises(ValueError, h.setSign, -50)
        self.assertEqual(h.variation.inDecimalDegrees, 1.)

        self.assertRaises(ValueError, h.setSign, 0)
        self.assertEqual(h.variation.inDecimalDegrees, 1.)

        self.assertRaises(ValueError, h.setSign, 50)
        self.assertEqual(h.variation.inDecimalDegrees, 1.)


    def test_setUnknownVariationSign(self):
        """
        Setting the sign on a heading with unknown variation raises
        C{ValueError}.
        """
        h = base.Heading.fromFloats(1.)
        self.assertIsNone(h.variation.inDecimalDegrees)
        self.assertRaises(ValueError, h.setSign, 1)



class CoordinateTests(TestCase):
    def test_float(self):
        """
        Coordinates can be converted to floats.
        """
        coordinate = base.Coordinate(10.0)
        self.assertEqual(float(coordinate), 10.0)


    def test_repr(self):
        """
        Coordinates that aren't explicitly latitudes or longitudes have an
        appropriate repr.
        """
        coordinate = base.Coordinate(10.0)
        expectedRepr = "<Angle of unknown type ({0} degrees)>".format(10.0)
        self.assertEqual(repr(coordinate), expectedRepr)


    def test_positiveLatitude(self):
        """
        Positive latitudes have a repr that specifies their type and value.
        """
        coordinate = base.Coordinate(10.0, Angles.LATITUDE)
        expectedRepr = "<Latitude ({0} degrees)>".format(10.0)
        self.assertEqual(repr(coordinate), expectedRepr)


    def test_negativeLatitude(self):
        """
        Negative latitudes have a repr that specifies their type and value.
        """
        coordinate = base.Coordinate(-50.0, Angles.LATITUDE)
        expectedRepr = "<Latitude ({0} degrees)>".format(-50.0)
        self.assertEqual(repr(coordinate), expectedRepr)


    def test_positiveLongitude(self):
        """
        Positive longitudes have a repr that specifies their type and value.
        """
        longitude = base.Coordinate(50.0, Angles.LONGITUDE)
        expectedRepr = "<Longitude ({0} degrees)>".format(50.0)
        self.assertEqual(repr(longitude), expectedRepr)


    def test_negativeLongitude(self):
        """
        Negative longitudes have a repr that specifies their type and value.
        """
        longitude = base.Coordinate(-50.0, Angles.LONGITUDE)
        expectedRepr = "<Longitude ({0} degrees)>".format(-50.0)
        self.assertEqual(repr(longitude), expectedRepr)


    def test_bogusCoordinateType(self):
        """
        Creating coordinates with bogus types rasies C{ValueError}.
        """
        self.assertRaises(ValueError, base.Coordinate, 150.0, "BOGUS")


    def test_angleTypeNotCoordinate(self):
        """
        Creating coordinates with angle types that aren't coordinates raises
        C{ValueError}.
        """
        self.assertRaises(ValueError, base.Coordinate, 150.0, Angles.HEADING)


    def test_equality(self):
        """
        Coordinates with the same value and type are equal.
        """
        def makeCoordinate():
            return base.Coordinate(1.0, Angles.LONGITUDE)
        self.assertEqual(makeCoordinate(), makeCoordinate())


    def test_differentAnglesInequality(self):
        """
        Coordinates with different values aren't equal.
        """
        c1 = base.Coordinate(1.0)
        c2 = base.Coordinate(-1.0)
        self.assertNotEqual(c1, c2)


    def test_differentTypesInequality(self):
        """
        Coordinates with the same values but different types aren't equal.
        """
        c1 = base.Coordinate(1.0, Angles.LATITUDE)
        c2 = base.Coordinate(1.0, Angles.LONGITUDE)
        self.assertNotEqual(c1, c2)


    def test_sign(self):
        """
        Setting the sign on a coordinate sets the sign of the value of the
        coordinate.
        """
        c = base.Coordinate(50., Angles.LATITUDE)
        c.setSign(1)
        self.assertEqual(c.inDecimalDegrees, 50.)
        c.setSign(-1)
        self.assertEqual(c.inDecimalDegrees, -50.)


    def test_badVariationSign(self):
        """
        Setting a bogus sign value (not -1 or 1) on a coordinate raises
        C{ValueError} and doesn't affect the coordinate.
        """
        value = 50.0
        c = base.Coordinate(value, Angles.LATITUDE)

        self.assertRaises(ValueError, c.setSign, -50)
        self.assertEqual(c.inDecimalDegrees, 50.)

        self.assertRaises(ValueError, c.setSign, 0)
        self.assertEqual(c.inDecimalDegrees, 50.)

        self.assertRaises(ValueError, c.setSign, 50)
        self.assertEqual(c.inDecimalDegrees, 50.)


    def test_northernHemisphere(self):
        """
        Positive latitudes are in the northern hemisphere.
        """
        coordinate = base.Coordinate(1.0, Angles.LATITUDE)
        self.assertEqual(coordinate.hemisphere, Directions.NORTH)


    def test_easternHemisphere(self):
        """
        Positive longitudes are in the eastern hemisphere.
        """
        coordinate = base.Coordinate(1.0, Angles.LONGITUDE)
        self.assertEqual(coordinate.hemisphere, Directions.EAST)


    def test_southernHemisphere(self):
        """
        Negative latitudes are in the southern hemisphere.
        """
        coordinate = base.Coordinate(-1.0, Angles.LATITUDE)
        self.assertEqual(coordinate.hemisphere, Directions.SOUTH)


    def test_westernHemisphere(self):
        """
        Negative longitudes are in the western hemisphere.
        """
        coordinate = base.Coordinate(-1.0, Angles.LONGITUDE)
        self.assertEqual(coordinate.hemisphere, Directions.WEST)


    def test_badHemisphere(self):
        """
        Accessing the hemisphere for a coordinate that can't compute it
        raises C{ValueError}.
        """
        coordinate = base.Coordinate(1.0, None)
        self.assertRaises(ValueError, lambda: coordinate.hemisphere)


    def test_latitudeTooLarge(self):
        """
        Creating a latitude with a value greater than or equal to 90 degrees
        raises C{ValueError}.
        """
        self.assertRaises(ValueError, _makeLatitude, 150.0)
        self.assertRaises(ValueError, _makeLatitude, 90.0)


    def test_latitudeTooSmall(self):
        """
        Creating a latitude with a value less than or equal to -90 degrees
        raises C{ValueError}.
        """
        self.assertRaises(ValueError, _makeLatitude, -150.0)
        self.assertRaises(ValueError, _makeLatitude, -90.0)


    def test_longitudeTooLarge(self):
        """
        Creating a longitude with a value greater than or equal to 180 degrees
        raises C{ValueError}.
        """
        self.assertRaises(ValueError, _makeLongitude, 250.0)
        self.assertRaises(ValueError, _makeLongitude, 180.0)


    def test_longitudeTooSmall(self):
        """
        Creating a longitude with a value less than or equal to -180 degrees
        raises C{ValueError}.
        """
        self.assertRaises(ValueError, _makeLongitude, -250.0)
        self.assertRaises(ValueError, _makeLongitude, -180.0)


    def test_inDegreesMinutesSeconds(self):
        """
        Coordinate values can be accessed in degrees, minutes, seconds.
        """
        c = base.Coordinate(50.5, Angles.LATITUDE)
        self.assertEqual(c.inDegreesMinutesSeconds, (50, 30, 0))

        c = base.Coordinate(50.213, Angles.LATITUDE)
        self.assertEqual(c.inDegreesMinutesSeconds, (50, 12, 46))


    def test_unknownAngleInDegreesMinutesSeconds(self):
        """
        If the vaue of a coordinate is L{None}, its values in degrees,
        minutes, seconds is also L{None}.
        """
        c = base.Coordinate(None, None)
        self.assertIsNone(c.inDegreesMinutesSeconds)



def _makeLatitude(value):
    """
    Builds and returns a latitude of given value.
    """
    return base.Coordinate(value, Angles.LATITUDE)



def _makeLongitude(value):
    """
    Builds and returns a longitude of given value.
    """
    return base.Coordinate(value, Angles.LONGITUDE)



class AltitudeTests(TestCase):
    """
    Tests for the L{twisted.positioning.base.Altitude} class.
    """
    def test_value(self):
        """
        Altitudes can be instantiated and reports the correct value in
        meters and feet, as well as when converted to float.
        """
        altitude = base.Altitude(1.)
        self.assertEqual(float(altitude), 1.)
        self.assertEqual(altitude.inMeters, 1.)
        self.assertEqual(altitude.inFeet, 1./base.METERS_PER_FOOT)


    def test_repr(self):
        """
        Altitudes report their type and value in their repr.
        """
        altitude = base.Altitude(1.)
        self.assertEqual(repr(altitude), "<Altitude (1.0 m)>")


    def test_equality(self):
        """
        Altitudes with equal values compare equal.
        """
        firstAltitude = base.Altitude(1.)
        secondAltitude = base.Altitude(1.)
        self.assertEqual(firstAltitude, secondAltitude)


    def test_inequality(self):
        """
        Altitudes with different values don't compare equal.
        """
        firstAltitude = base.Altitude(1.)
        secondAltitude = base.Altitude(-1.)
        self.assertNotEqual(firstAltitude, secondAltitude)



class SpeedTests(TestCase):
    """
    Tests for the L{twisted.positioning.base.Speed} class.
    """
    def test_value(self):
        """
        Speeds can be instantiated, and report their value in meters
        per second, and can be converted to floats.
        """
        speed = base.Speed(50.0)
        self.assertEqual(speed.inMetersPerSecond, 50.0)
        self.assertEqual(float(speed), 50.0)


    def test_repr(self):
        """
        Speeds report their type and value in their repr.
        """
        speed = base.Speed(50.0)
        self.assertEqual(repr(speed), "<Speed (50.0 m/s)>")


    def test_negativeSpeeds(self):
        """
        Creating a negative speed raises C{ValueError}.
        """
        self.assertRaises(ValueError, base.Speed, -1.0)


    def test_inKnots(self):
        """
        A speed can be converted into its value in knots.
        """
        speed = base.Speed(1.0)
        self.assertEqual(1/base.MPS_PER_KNOT, speed.inKnots)


    def test_asFloat(self):
        """
        A speed can be converted into a C{float}.
        """
        self.assertEqual(1.0, float(base.Speed(1.0)))



class ClimbTests(TestCase):
    """
    Tests for L{twisted.positioning.base.Climb}.
    """
    def test_simple(self):
        """
        Speeds can be instantiated, and report their value in meters
        per second, and can be converted to floats.
        """
        climb = base.Climb(42.)
        self.assertEqual(climb.inMetersPerSecond, 42.)
        self.assertEqual(float(climb), 42.)


    def test_repr(self):
        """
        Climbs report their type and value in their repr.
        """
        climb = base.Climb(42.)
        self.assertEqual(repr(climb), "<Climb (42.0 m/s)>")


    def test_negativeClimbs(self):
        """
        Climbs can have negative values, and still report that value
        in meters per second and when converted to floats.
        """
        climb = base.Climb(-42.)
        self.assertEqual(climb.inMetersPerSecond, -42.)
        self.assertEqual(float(climb), -42.)


    def test_speedInKnots(self):
        """
        A climb can be converted into its value in knots.
        """
        climb = base.Climb(1.0)
        self.assertEqual(1/base.MPS_PER_KNOT, climb.inKnots)


    def test_asFloat(self):
        """
        A climb can be converted into a C{float}.
        """
        self.assertEqual(1.0, float(base.Climb(1.0)))



class PositionErrorTests(TestCase):
    """
    Tests for L{twisted.positioning.base.PositionError}.
    """
    def test_allUnset(self):
        """
        In an empty L{base.PositionError} with no invariant testing, all
        dilutions of positions are L{None}.
        """
        positionError = base.PositionError()
        self.assertIsNone(positionError.pdop)
        self.assertIsNone(positionError.hdop)
        self.assertIsNone(positionError.vdop)


    def test_allUnsetWithInvariant(self):
        """
        In an empty L{base.PositionError} with invariant testing, all
        dilutions of positions are L{None}.
        """
        positionError = base.PositionError(testInvariant=True)
        self.assertIsNone(positionError.pdop)
        self.assertIsNone(positionError.hdop)
        self.assertIsNone(positionError.vdop)


    def test_withoutInvariant(self):
        """
        L{base.PositionError}s can be instantiated with just a HDOP.
        """
        positionError = base.PositionError(hdop=1.0)
        self.assertEqual(positionError.hdop, 1.0)


    def test_withInvariant(self):
        """
        Creating a simple L{base.PositionError} with just a HDOP while
        checking the invariant works.
        """
        positionError = base.PositionError(hdop=1.0, testInvariant=True)
        self.assertEqual(positionError.hdop, 1.0)


    def test_invalidWithoutInvariant(self):
        """
        Creating a L{base.PositionError} with values set to an impossible
        combination works if the invariant is not checked.
        """
        error = base.PositionError(pdop=1.0, vdop=1.0, hdop=1.0)
        self.assertEqual(error.pdop, 1.0)
        self.assertEqual(error.hdop, 1.0)
        self.assertEqual(error.vdop, 1.0)


    def test_invalidWithInvariant(self):
        """
        Creating a L{base.PositionError} with values set to an impossible
        combination raises C{ValueError} if the invariant is being tested.
        """
        self.assertRaises(ValueError, base.PositionError,
                          pdop=1.0, vdop=1.0, hdop=1.0, testInvariant=True)


    def test_setDOPWithoutInvariant(self):
        """
        You can set the PDOP value to value inconsisted with HDOP and VDOP
        when not checking the invariant.
        """
        pe = base.PositionError(hdop=1.0, vdop=1.0)
        pe.pdop = 100.0
        self.assertEqual(pe.pdop, 100.0)


    def test_setDOPWithInvariant(self):
        """
        Attempting to set the PDOP value to value inconsisted with HDOP and
        VDOP when checking the invariant raises C{ValueError}.
        """
        pe = base.PositionError(hdop=1.0, vdop=1.0, testInvariant=True)
        pdop = pe.pdop

        def setPDOP(pe):
            pe.pdop = 100.0

        self.assertRaises(ValueError, setPDOP, pe)
        self.assertEqual(pe.pdop, pdop)


    REPR_TEMPLATE = "<PositionError (pdop: %s, hdop: %s, vdop: %s)>"


    def _testDOP(self, pe, pdop, hdop, vdop):
        """
        Tests the DOP values in a position error, and the repr of that
        position error.

        @param pe: The position error under test.
        @type pe: C{PositionError}
        @param pdop: The expected position dilution of precision.
        @type pdop: C{float} or L{None}
        @param hdop: The expected horizontal dilution of precision.
        @type hdop: C{float} or L{None}
        @param vdop: The expected vertical dilution of precision.
        @type vdop: C{float} or L{None}
        """
        self.assertEqual(pe.pdop, pdop)
        self.assertEqual(pe.hdop, hdop)
        self.assertEqual(pe.vdop, vdop)
        self.assertEqual(repr(pe), self.REPR_TEMPLATE % (pdop, hdop, vdop))


    def test_positionAndHorizontalSet(self):
        """
        The VDOP is correctly determined from PDOP and HDOP.
        """
        pdop, hdop = 2.0, 1.0
        vdop = (pdop**2 - hdop**2)**.5
        pe = base.PositionError(pdop=pdop, hdop=hdop)
        self._testDOP(pe, pdop, hdop, vdop)


    def test_positionAndVerticalSet(self):
        """
        The HDOP is correctly determined from PDOP and VDOP.
        """
        pdop, vdop = 2.0, 1.0
        hdop = (pdop**2 - vdop**2)**.5
        pe = base.PositionError(pdop=pdop, vdop=vdop)
        self._testDOP(pe, pdop, hdop, vdop)


    def test_horizontalAndVerticalSet(self):
        """
        The PDOP is correctly determined from HDOP and VDOP.
        """
        hdop, vdop = 1.0, 1.0
        pdop = (hdop**2 + vdop**2)**.5
        pe = base.PositionError(hdop=hdop, vdop=vdop)
        self._testDOP(pe, pdop, hdop, vdop)



class BeaconInformationTests(TestCase):
    """
    Tests for L{twisted.positioning.base.BeaconInformation}.
    """
    def test_minimal(self):
        """
        For an empty beacon information object, the number of used
        beacons is zero, the number of seen beacons is zero, and the
        repr of the object reflects that.
        """
        bi = base.BeaconInformation()
        self.assertEqual(len(bi.usedBeacons), 0)
        expectedRepr = ("<BeaconInformation ("
                        "used beacons (0): [], "
                        "unused beacons: [])>")
        self.assertEqual(repr(bi), expectedRepr)


    satelliteKwargs = {"azimuth": 1, "elevation": 1, "signalToNoiseRatio": 1.}


    def test_simple(self):
        """
        Tests a beacon information with a bunch of satellites, none of
        which used in computing a fix.
        """
        def _buildSatellite(**kw):
            kwargs = dict(self.satelliteKwargs)
            kwargs.update(kw)
            return base.Satellite(**kwargs)

        beacons = set()
        for prn in range(1, 10):
            beacons.add(_buildSatellite(identifier=prn))

        bi = base.BeaconInformation(beacons)

        self.assertEqual(len(bi.seenBeacons), 9)
        self.assertEqual(len(bi.usedBeacons), 0)
        self.assertEqual(repr(bi),
            "<BeaconInformation (used beacons (0): [], "
            "unused beacons: ["
            "<Satellite (1), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (2), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (3), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (4), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (5), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (6), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (7), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (8), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (9), azimuth: 1, elevation: 1, snr: 1.0>"
            "])>")


    def test_someSatellitesUsed(self):
        """
        Tests a beacon information with a bunch of satellites, some of
        them used in computing a fix.
        """
        bi = base.BeaconInformation()

        for prn in range(1, 10):
            satellite = base.Satellite(identifier=prn, **self.satelliteKwargs)
            bi.seenBeacons.add(satellite)
            if prn % 2:
                bi.usedBeacons.add(satellite)

        self.assertEqual(len(bi.seenBeacons), 9)
        self.assertEqual(len(bi.usedBeacons), 5)

        self.assertEqual(repr(bi),
            "<BeaconInformation (used beacons (5): ["
            "<Satellite (1), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (3), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (5), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (7), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (9), azimuth: 1, elevation: 1, snr: 1.0>], "
            "unused beacons: ["
            "<Satellite (2), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (4), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (6), azimuth: 1, elevation: 1, snr: 1.0>, "
            "<Satellite (8), azimuth: 1, elevation: 1, snr: 1.0>])>")



class PositioningBeaconTests(TestCase):
    """
    Tests for L{base.PositioningBeacon}.
    """
    def test_interface(self):
        """
        Tests that L{base.PositioningBeacon} implements L{IPositioningBeacon}.
        """
        implements = IPositioningBeacon.implementedBy(base.PositioningBeacon)
        self.assertTrue(implements)
        verify.verifyObject(IPositioningBeacon, base.PositioningBeacon(1))


    def test_repr(self):
        """
        Tests the repr of a positioning beacon.
        """
        self.assertEqual(repr(base.PositioningBeacon("A")), "<Beacon (A)>")



class SatelliteTests(TestCase):
    """
    Tests for L{twisted.positioning.base.Satellite}.
    """
    def test_minimal(self):
        """
        Tests a minimal satellite that only has a known PRN.

        Tests that the azimuth, elevation and signal to noise ratios
        are L{None} and verifies the repr.
        """
        s = base.Satellite(1)
        self.assertEqual(s.identifier, 1)
        self.assertIsNone(s.azimuth)
        self.assertIsNone(s.elevation)
        self.assertIsNone(s.signalToNoiseRatio)
        self.assertEqual(repr(s), "<Satellite (1), azimuth: None, "
                                   "elevation: None, snr: None>")


    def test_simple(self):
        """
        Tests a minimal satellite that only has a known PRN.

        Tests that the azimuth, elevation and signal to noise ratios
        are correct and verifies the repr.
        """
        s = base.Satellite(identifier=1,
                           azimuth=270.,
                           elevation=30.,
                           signalToNoiseRatio=25.)

        self.assertEqual(s.identifier, 1)
        self.assertEqual(s.azimuth, 270.)
        self.assertEqual(s.elevation, 30.)
        self.assertEqual(s.signalToNoiseRatio, 25.)
        self.assertEqual(repr(s), "<Satellite (1), azimuth: 270.0, "
                                   "elevation: 30.0, snr: 25.0>")

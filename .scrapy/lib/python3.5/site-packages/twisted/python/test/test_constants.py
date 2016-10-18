# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Unit tests for L{twisted.python.constants}.
"""

from __future__ import division, absolute_import

from twisted.trial.unittest import TestCase

from twisted.python.constants import (
    NamedConstant, Names, ValueConstant, Values, FlagConstant, Flags
)



class NamedConstantTests(TestCase):
    """
    Tests for the L{twisted.python.constants.NamedConstant} class which is used
    to represent individual values.
    """
    def setUp(self):
        """
        Create a dummy container into which constants can be placed.
        """
        class foo(Names):
            pass
        self.container = foo


    def test_name(self):
        """
        The C{name} attribute of a L{NamedConstant} refers to the value passed
        for the C{name} parameter to C{_realize}.
        """
        name = NamedConstant()
        name._realize(self.container, "bar", None)
        self.assertEqual("bar", name.name)


    def test_representation(self):
        """
        The string representation of an instance of L{NamedConstant} includes
        the container the instances belongs to as well as the instance's name.
        """
        name = NamedConstant()
        name._realize(self.container, "bar", None)
        self.assertEqual("<foo=bar>", repr(name))


    def test_equality(self):
        """
        A L{NamedConstant} instance compares equal to itself.
        """
        name = NamedConstant()
        name._realize(self.container, "bar", None)
        self.assertTrue(name == name)
        self.assertFalse(name != name)


    def test_nonequality(self):
        """
        Two different L{NamedConstant} instances do not compare equal to each
        other.
        """
        first = NamedConstant()
        first._realize(self.container, "bar", None)
        second = NamedConstant()
        second._realize(self.container, "bar", None)
        self.assertFalse(first == second)
        self.assertTrue(first != second)


    def test_hash(self):
        """
        Because two different L{NamedConstant} instances do not compare as
        equal to each other, they also have different hashes to avoid
        collisions when added to a C{dict} or C{set}.
        """
        first = NamedConstant()
        first._realize(self.container, "bar", None)
        second = NamedConstant()
        second._realize(self.container, "bar", None)
        self.assertNotEqual(hash(first), hash(second))



class _ConstantsTestsMixin(object):
    """
    Mixin defining test helpers common to multiple types of constants
    collections.
    """
    def _notInstantiableTest(self, name, cls):
        """
        Assert that an attempt to instantiate the constants class raises
        C{TypeError}.

        @param name: A C{str} giving the name of the constants collection.
        @param cls: The constants class to test.
        """
        exc = self.assertRaises(TypeError, cls)
        self.assertEqual(name + " may not be instantiated.", str(exc))


    def _initializedOnceTest(self, container, constantName):
        """
        Assert that C{container._enumerants} does not change as a side-effect
        of one of its attributes being accessed.

        @param container: A L{_ConstantsContainer} subclass which will be
            tested.
        @param constantName: The name of one of the constants which is an
            attribute of C{container}.
        """
        first = container._enumerants

        # Accessing an attribute of the container should not have any
        # observable side-effect on the _enumerants attribute.
        getattr(container, constantName)

        second = container._enumerants
        self.assertIs(first, second)



class NamesTests(TestCase, _ConstantsTestsMixin):
    """
    Tests for L{twisted.python.constants.Names}, a base class for containers of
    related constraints.
    """
    def setUp(self):
        """
        Create a fresh new L{Names} subclass for each unit test to use.  Since
        L{Names} is stateful, re-using the same subclass across test methods
        makes exercising all of the implementation code paths difficult.
        """
        class METHOD(Names):
            """
            A container for some named constants to use in unit tests for
            L{Names}.
            """
            GET = NamedConstant()
            PUT = NamedConstant()
            POST = NamedConstant()
            DELETE = NamedConstant()

            extra = object()

        self.METHOD = METHOD


    def test_notInstantiable(self):
        """
        A subclass of L{Names} raises C{TypeError} if an attempt is made to
        instantiate it.
        """
        self._notInstantiableTest("METHOD", self.METHOD)


    def test_symbolicAttributes(self):
        """
        Each name associated with a L{NamedConstant} instance in the definition
        of a L{Names} subclass is available as an attribute on the resulting
        class.
        """
        self.assertTrue(hasattr(self.METHOD, "GET"))
        self.assertTrue(hasattr(self.METHOD, "PUT"))
        self.assertTrue(hasattr(self.METHOD, "POST"))
        self.assertTrue(hasattr(self.METHOD, "DELETE"))


    def test_withoutOtherAttributes(self):
        """
        As usual, names not defined in the class scope of a L{Names}
        subclass are not available as attributes on the resulting class.
        """
        self.assertFalse(hasattr(self.METHOD, "foo"))


    def test_representation(self):
        """
        The string representation of a constant on a L{Names} subclass includes
        the name of the L{Names} subclass and the name of the constant itself.
        """
        self.assertEqual("<METHOD=GET>", repr(self.METHOD.GET))


    def test_lookupByName(self):
        """
        Constants can be looked up by name using L{Names.lookupByName}.
        """
        method = self.METHOD.lookupByName("GET")
        self.assertIs(self.METHOD.GET, method)


    def test_notLookupMissingByName(self):
        """
        Names not defined with a L{NamedConstant} instance cannot be looked up
        using L{Names.lookupByName}.
        """
        self.assertRaises(ValueError, self.METHOD.lookupByName, "lookupByName")
        self.assertRaises(ValueError, self.METHOD.lookupByName, "__init__")
        self.assertRaises(ValueError, self.METHOD.lookupByName, "foo")
        self.assertRaises(ValueError, self.METHOD.lookupByName, "extra")


    def test_name(self):
        """
        The C{name} attribute of one of the named constants gives that
        constant's name.
        """
        self.assertEqual("GET", self.METHOD.GET.name)


    def test_attributeIdentity(self):
        """
        Repeated access of an attribute associated with a L{NamedConstant}
        value in a L{Names} subclass results in the same object.
        """
        self.assertIs(self.METHOD.GET, self.METHOD.GET)


    def test_iterconstants(self):
        """
        L{Names.iterconstants} returns an iterator over all of the constants
        defined in the class, in the order they were defined.
        """
        constants = list(self.METHOD.iterconstants())
        self.assertEqual(
            [self.METHOD.GET, self.METHOD.PUT,
             self.METHOD.POST, self.METHOD.DELETE],
            constants)


    def test_attributeIterconstantsIdentity(self):
        """
        The constants returned from L{Names.iterconstants} are identical to the
        constants accessible using attributes.
        """
        constants = list(self.METHOD.iterconstants())
        self.assertIs(self.METHOD.GET, constants[0])
        self.assertIs(self.METHOD.PUT, constants[1])
        self.assertIs(self.METHOD.POST, constants[2])
        self.assertIs(self.METHOD.DELETE, constants[3])


    def test_iterconstantsIdentity(self):
        """
        The constants returned from L{Names.iterconstants} are identical on
        each call to that method.
        """
        constants = list(self.METHOD.iterconstants())
        again = list(self.METHOD.iterconstants())
        self.assertIs(again[0], constants[0])
        self.assertIs(again[1], constants[1])
        self.assertIs(again[2], constants[2])
        self.assertIs(again[3], constants[3])


    def test_initializedOnce(self):
        """
        L{Names._enumerants} is initialized once and its value re-used on
        subsequent access.
        """
        self._initializedOnceTest(self.METHOD, "GET")


    def test_asForeignClassAttribute(self):
        """
        A constant defined on a L{Names} subclass may be set as an attribute of
        another class and then retrieved using that attribute.
        """
        class Another(object):
            something = self.METHOD.GET

        self.assertIs(self.METHOD.GET, Another.something)


    def test_asForeignClassAttributeViaInstance(self):
        """
        A constant defined on a L{Names} subclass may be set as an attribute of
        another class and then retrieved from an instance of that class using
        that attribute.
        """
        class Another(object):
            something = self.METHOD.GET

        self.assertIs(self.METHOD.GET, Another().something)


    def test_notAsAlternateContainerAttribute(self):
        """
        It is explicitly disallowed (via a L{ValueError}) to use a constant
        defined on a L{Names} subclass as the value of an attribute of another
        L{Names} subclass.
        """
        def defineIt():
            class AnotherNames(Names):
                something = self.METHOD.GET

        exc = self.assertRaises(ValueError, defineIt)
        self.assertEqual(
            "Cannot use <METHOD=GET> as the value of an attribute on "
            "AnotherNames",
            str(exc))



class ValuesTests(TestCase, _ConstantsTestsMixin):
    """
    Tests for L{twisted.python.constants.Names}, a base class for containers of
    related constraints with arbitrary values.
    """
    def setUp(self):
        """
        Create a fresh new L{Values} subclass for each unit test to use.  Since
        L{Values} is stateful, re-using the same subclass across test methods
        makes exercising all of the implementation code paths difficult.
        """
        class STATUS(Values):
            OK = ValueConstant("200")
            NOT_FOUND = ValueConstant("404")

        self.STATUS = STATUS


    def test_notInstantiable(self):
        """
        A subclass of L{Values} raises C{TypeError} if an attempt is made to
        instantiate it.
        """
        self._notInstantiableTest("STATUS", self.STATUS)


    def test_symbolicAttributes(self):
        """
        Each name associated with a L{ValueConstant} instance in the definition
        of a L{Values} subclass is available as an attribute on the resulting
        class.
        """
        self.assertTrue(hasattr(self.STATUS, "OK"))
        self.assertTrue(hasattr(self.STATUS, "NOT_FOUND"))


    def test_withoutOtherAttributes(self):
        """
        As usual, names not defined in the class scope of a L{Values}
        subclass are not available as attributes on the resulting class.
        """
        self.assertFalse(hasattr(self.STATUS, "foo"))


    def test_representation(self):
        """
        The string representation of a constant on a L{Values} subclass
        includes the name of the L{Values} subclass and the name of the
        constant itself.
        """
        self.assertEqual("<STATUS=OK>", repr(self.STATUS.OK))


    def test_lookupByName(self):
        """
        Constants can be looked up by name using L{Values.lookupByName}.
        """
        method = self.STATUS.lookupByName("OK")
        self.assertIs(self.STATUS.OK, method)


    def test_notLookupMissingByName(self):
        """
        Names not defined with a L{ValueConstant} instance cannot be looked up
        using L{Values.lookupByName}.
        """
        self.assertRaises(ValueError, self.STATUS.lookupByName, "lookupByName")
        self.assertRaises(ValueError, self.STATUS.lookupByName, "__init__")
        self.assertRaises(ValueError, self.STATUS.lookupByName, "foo")


    def test_lookupByValue(self):
        """
        Constants can be looked up by their associated value, defined by the
        argument passed to L{ValueConstant}, using L{Values.lookupByValue}.
        """
        status = self.STATUS.lookupByValue("200")
        self.assertIs(self.STATUS.OK, status)


    def test_lookupDuplicateByValue(self):
        """
        If more than one constant is associated with a particular value,
        L{Values.lookupByValue} returns whichever of them is defined first.
        """
        class TRANSPORT_MESSAGE(Values):
            """
            Message types supported by an SSH transport.
            """
            KEX_DH_GEX_REQUEST_OLD = ValueConstant(30)
            KEXDH_INIT = ValueConstant(30)

        self.assertIs(
            TRANSPORT_MESSAGE.lookupByValue(30),
            TRANSPORT_MESSAGE.KEX_DH_GEX_REQUEST_OLD)


    def test_notLookupMissingByValue(self):
        """
        L{Values.lookupByValue} raises L{ValueError} when called with a value
        with which no constant is associated.
        """
        self.assertRaises(ValueError, self.STATUS.lookupByValue, "OK")
        self.assertRaises(ValueError, self.STATUS.lookupByValue, 200)
        self.assertRaises(ValueError, self.STATUS.lookupByValue, "200.1")


    def test_name(self):
        """
        The C{name} attribute of one of the constants gives that constant's
        name.
        """
        self.assertEqual("OK", self.STATUS.OK.name)


    def test_attributeIdentity(self):
        """
        Repeated access of an attribute associated with a L{ValueConstant}
        value in a L{Values} subclass results in the same object.
        """
        self.assertIs(self.STATUS.OK, self.STATUS.OK)


    def test_iterconstants(self):
        """
        L{Values.iterconstants} returns an iterator over all of the constants
        defined in the class, in the order they were defined.
        """
        constants = list(self.STATUS.iterconstants())
        self.assertEqual(
            [self.STATUS.OK, self.STATUS.NOT_FOUND],
            constants)


    def test_attributeIterconstantsIdentity(self):
        """
        The constants returned from L{Values.iterconstants} are identical to
        the constants accessible using attributes.
        """
        constants = list(self.STATUS.iterconstants())
        self.assertIs(self.STATUS.OK, constants[0])
        self.assertIs(self.STATUS.NOT_FOUND, constants[1])


    def test_iterconstantsIdentity(self):
        """
        The constants returned from L{Values.iterconstants} are identical on
        each call to that method.
        """
        constants = list(self.STATUS.iterconstants())
        again = list(self.STATUS.iterconstants())
        self.assertIs(again[0], constants[0])
        self.assertIs(again[1], constants[1])


    def test_initializedOnce(self):
        """
        L{Values._enumerants} is initialized once and its value re-used on
        subsequent access.
        """
        self._initializedOnceTest(self.STATUS, "OK")



class _FlagsTestsMixin(object):
    """
    Mixin defining setup code for any tests for L{Flags} subclasses.

    @ivar FXF: A L{Flags} subclass created for each test method.
    """
    def setUp(self):
        """
        Create a fresh new L{Flags} subclass for each unit test to use.  Since
        L{Flags} is stateful, re-using the same subclass across test methods
        makes exercising all of the implementation code paths difficult.
        """
        class FXF(Flags):
            # Implicitly assign three flag values based on definition order
            READ = FlagConstant()
            WRITE = FlagConstant()
            APPEND = FlagConstant()

            # Explicitly assign one flag value by passing it in
            EXCLUSIVE = FlagConstant(0x20)

            # Implicitly assign another flag value, following the previously
            # specified explicit value.
            TEXT = FlagConstant()

        self.FXF = FXF



class FlagsTests(_FlagsTestsMixin, TestCase, _ConstantsTestsMixin):
    """
    Tests for L{twisted.python.constants.Flags}, a base class for containers of
    related, combinable flag or bitvector-like constants.
    """
    def test_notInstantiable(self):
        """
        A subclass of L{Flags} raises L{TypeError} if an attempt is made to
        instantiate it.
        """
        self._notInstantiableTest("FXF", self.FXF)


    def test_symbolicAttributes(self):
        """
        Each name associated with a L{FlagConstant} instance in the definition
        of a L{Flags} subclass is available as an attribute on the resulting
        class.
        """
        self.assertTrue(hasattr(self.FXF, "READ"))
        self.assertTrue(hasattr(self.FXF, "WRITE"))
        self.assertTrue(hasattr(self.FXF, "APPEND"))
        self.assertTrue(hasattr(self.FXF, "EXCLUSIVE"))
        self.assertTrue(hasattr(self.FXF, "TEXT"))


    def test_withoutOtherAttributes(self):
        """
        As usual, names not defined in the class scope of a L{Flags} subclass
        are not available as attributes on the resulting class.
        """
        self.assertFalse(hasattr(self.FXF, "foo"))


    def test_representation(self):
        """
        The string representation of a constant on a L{Flags} subclass includes
        the name of the L{Flags} subclass and the name of the constant itself.
        """
        self.assertEqual("<FXF=READ>", repr(self.FXF.READ))


    def test_lookupByName(self):
        """
        Constants can be looked up by name using L{Flags.lookupByName}.
        """
        flag = self.FXF.lookupByName("READ")
        self.assertIs(self.FXF.READ, flag)


    def test_notLookupMissingByName(self):
        """
        Names not defined with a L{FlagConstant} instance cannot be looked up
        using L{Flags.lookupByName}.
        """
        self.assertRaises(ValueError, self.FXF.lookupByName, "lookupByName")
        self.assertRaises(ValueError, self.FXF.lookupByName, "__init__")
        self.assertRaises(ValueError, self.FXF.lookupByName, "foo")


    def test_lookupByValue(self):
        """
        Constants can be looked up by their associated value, defined
        implicitly by the position in which the constant appears in the class
        definition or explicitly by the argument passed to L{FlagConstant}.
        """
        flag = self.FXF.lookupByValue(0x01)
        self.assertIs(flag, self.FXF.READ)

        flag = self.FXF.lookupByValue(0x02)
        self.assertIs(flag, self.FXF.WRITE)

        flag = self.FXF.lookupByValue(0x04)
        self.assertIs(flag, self.FXF.APPEND)

        flag = self.FXF.lookupByValue(0x20)
        self.assertIs(flag, self.FXF.EXCLUSIVE)

        flag = self.FXF.lookupByValue(0x40)
        self.assertIs(flag, self.FXF.TEXT)


    def test_lookupDuplicateByValue(self):
        """
        If more than one constant is associated with a particular value,
        L{Flags.lookupByValue} returns whichever of them is defined first.
        """
        class TIMEX(Flags):
            # (timex.mode)
            ADJ_OFFSET = FlagConstant(0x0001)  # time offset

            #  xntp 3.4 compatibility names
            MOD_OFFSET = FlagConstant(0x0001)

        self.assertIs(TIMEX.lookupByValue(0x0001), TIMEX.ADJ_OFFSET)


    def test_notLookupMissingByValue(self):
        """
        L{Flags.lookupByValue} raises L{ValueError} when called with a value
        with which no constant is associated.
        """
        self.assertRaises(ValueError, self.FXF.lookupByValue, 0x10)


    def test_name(self):
        """
        The C{name} attribute of one of the constants gives that constant's
        name.
        """
        self.assertEqual("READ", self.FXF.READ.name)


    def test_attributeIdentity(self):
        """
        Repeated access of an attribute associated with a L{FlagConstant} value
        in a L{Flags} subclass results in the same object.
        """
        self.assertIs(self.FXF.READ, self.FXF.READ)


    def test_iterconstants(self):
        """
        L{Flags.iterconstants} returns an iterator over all of the constants
        defined in the class, in the order they were defined.
        """
        constants = list(self.FXF.iterconstants())
        self.assertEqual(
            [self.FXF.READ, self.FXF.WRITE, self.FXF.APPEND,
             self.FXF.EXCLUSIVE, self.FXF.TEXT],
            constants)


    def test_attributeIterconstantsIdentity(self):
        """
        The constants returned from L{Flags.iterconstants} are identical to the
        constants accessible using attributes.
        """
        constants = list(self.FXF.iterconstants())
        self.assertIs(self.FXF.READ, constants[0])
        self.assertIs(self.FXF.WRITE, constants[1])
        self.assertIs(self.FXF.APPEND, constants[2])
        self.assertIs(self.FXF.EXCLUSIVE, constants[3])
        self.assertIs(self.FXF.TEXT, constants[4])


    def test_iterconstantsIdentity(self):
        """
        The constants returned from L{Flags.iterconstants} are identical on
        each call to that method.
        """
        constants = list(self.FXF.iterconstants())
        again = list(self.FXF.iterconstants())
        self.assertIs(again[0], constants[0])
        self.assertIs(again[1], constants[1])
        self.assertIs(again[2], constants[2])
        self.assertIs(again[3], constants[3])
        self.assertIs(again[4], constants[4])


    def test_initializedOnce(self):
        """
        L{Flags._enumerants} is initialized once and its value re-used on
        subsequent access.
        """
        self._initializedOnceTest(self.FXF, "READ")



class FlagConstantSimpleOrTests(_FlagsTestsMixin, TestCase):
    """
    Tests for the C{|} operator as defined for L{FlagConstant} instances, used
    to create new L{FlagConstant} instances representing both of two existing
    L{FlagConstant} instances from the same L{Flags} class.
    """
    def test_value(self):
        """
        The value of the L{FlagConstant} which results from C{|} has all of the
        bits set which were set in either of the values of the two original
        constants.
        """
        flag = self.FXF.READ | self.FXF.WRITE
        self.assertEqual(
            self.FXF.READ.value | self.FXF.WRITE.value, flag.value
        )


    def test_name(self):
        """
        The name of the L{FlagConstant} instance which results from C{|}
        includes the names of both of the two original constants.
        """
        flag = self.FXF.READ | self.FXF.WRITE
        self.assertEqual("{READ,WRITE}", flag.name)


    def test_representation(self):
        """
        The string representation of a L{FlagConstant} instance which results
        from C{|} includes the names of both of the two original constants.
        """
        flag = self.FXF.READ | self.FXF.WRITE
        self.assertEqual("<FXF={READ,WRITE}>", repr(flag))


    def test_iterate(self):
        """
        A L{FlagConstant} instance which results from C{|} can be
        iterated upon to yield the original constants.
        """
        self.assertEqual(
            set(self.FXF.WRITE & self.FXF.READ),  # No flags
            set(()))
        self.assertEqual(
            set(self.FXF.WRITE),
            set((self.FXF.WRITE,)))
        self.assertEqual(
            set(self.FXF.WRITE | self.FXF.EXCLUSIVE),
            set((self.FXF.WRITE, self.FXF.EXCLUSIVE)))


    def test_membership(self):
        """
        A L{FlagConstant} instance which results from C{|} can be
        tested for membership.
        """
        flags = self.FXF.WRITE | self.FXF.EXCLUSIVE
        self.assertIn(self.FXF.WRITE, flags)
        self.assertNotIn(self.FXF.READ, flags)


    def test_truthiness(self):
        """
        Empty flags is false, non-empty flags is true.
        """
        self.assertTrue(self.FXF.WRITE)
        self.assertTrue(self.FXF.WRITE | self.FXF.EXCLUSIVE)
        self.assertFalse(self.FXF.WRITE & self.FXF.EXCLUSIVE)



class FlagConstantSimpleAndTests(_FlagsTestsMixin, TestCase):
    """
    Tests for the C{&} operator as defined for L{FlagConstant} instances, used
    to create new L{FlagConstant} instances representing the common parts of
    two existing L{FlagConstant} instances from the same L{Flags} class.
    """
    def test_value(self):
        """
        The value of the L{FlagConstant} which results from C{&} has all of the
        bits set which were set in both of the values of the two original
        constants.
        """
        readWrite = (self.FXF.READ | self.FXF.WRITE)
        writeAppend = (self.FXF.WRITE | self.FXF.APPEND)
        flag = readWrite & writeAppend
        self.assertEqual(self.FXF.WRITE.value, flag.value)


    def test_name(self):
        """
        The name of the L{FlagConstant} instance which results from C{&}
        includes the names of only the flags which were set in both of the two
        original constants.
        """
        readWrite = (self.FXF.READ | self.FXF.WRITE)
        writeAppend = (self.FXF.WRITE | self.FXF.APPEND)
        flag = readWrite & writeAppend
        self.assertEqual("WRITE", flag.name)


    def test_representation(self):
        """
        The string representation of a L{FlagConstant} instance which results
        from C{&} includes the names of only the flags which were set in both
        both of the two original constants.
        """
        readWrite = (self.FXF.READ | self.FXF.WRITE)
        writeAppend = (self.FXF.WRITE | self.FXF.APPEND)
        flag = readWrite & writeAppend
        self.assertEqual("<FXF=WRITE>", repr(flag))



class FlagConstantSimpleExclusiveOrTests(_FlagsTestsMixin, TestCase):
    """
    Tests for the C{^} operator as defined for L{FlagConstant} instances, used
    to create new L{FlagConstant} instances representing the uncommon parts of
    two existing L{FlagConstant} instances from the same L{Flags} class.
    """
    def test_value(self):
        """
        The value of the L{FlagConstant} which results from C{^} has all of the
        bits set which were set in exactly one of the values of the two
        original constants.
        """
        readWrite = (self.FXF.READ | self.FXF.WRITE)
        writeAppend = (self.FXF.WRITE | self.FXF.APPEND)
        flag = readWrite ^ writeAppend
        self.assertEqual(
            self.FXF.READ.value | self.FXF.APPEND.value, flag.value
        )


    def test_name(self):
        """
        The name of the L{FlagConstant} instance which results from C{^}
        includes the names of only the flags which were set in exactly one of
        the two original constants.
        """
        readWrite = (self.FXF.READ | self.FXF.WRITE)
        writeAppend = (self.FXF.WRITE | self.FXF.APPEND)
        flag = readWrite ^ writeAppend
        self.assertEqual("{APPEND,READ}", flag.name)


    def test_representation(self):
        """
        The string representation of a L{FlagConstant} instance which results
        from C{^} includes the names of only the flags which were set in
        exactly one of the two original constants.
        """
        readWrite = (self.FXF.READ | self.FXF.WRITE)
        writeAppend = (self.FXF.WRITE | self.FXF.APPEND)
        flag = readWrite ^ writeAppend
        self.assertEqual("<FXF={APPEND,READ}>", repr(flag))



class FlagConstantNegationTests(_FlagsTestsMixin, TestCase):
    """
    Tests for the C{~} operator as defined for L{FlagConstant} instances, used
    to create new L{FlagConstant} instances representing all the flags from a
    L{Flags} class not set in a particular L{FlagConstant} instance.
    """
    def test_value(self):
        """
        The value of the L{FlagConstant} which results from C{~} has all of the
        bits set which were not set in the original constant.
        """
        flag = ~self.FXF.READ
        self.assertEqual(
            self.FXF.WRITE.value |
            self.FXF.APPEND.value |
            self.FXF.EXCLUSIVE.value |
            self.FXF.TEXT.value,
            flag.value)

        flag = ~self.FXF.WRITE
        self.assertEqual(
            self.FXF.READ.value |
            self.FXF.APPEND.value |
            self.FXF.EXCLUSIVE.value |
            self.FXF.TEXT.value,
            flag.value)


    def test_name(self):
        """
        The name of the L{FlagConstant} instance which results from C{~}
        includes the names of all the flags which were not set in the original
        constant.
        """
        flag = ~self.FXF.WRITE
        self.assertEqual("{APPEND,EXCLUSIVE,READ,TEXT}", flag.name)


    def test_representation(self):
        """
        The string representation of a L{FlagConstant} instance which results
        from C{~} includes the names of all the flags which were not set in the
        original constant.
        """
        flag = ~self.FXF.WRITE
        self.assertEqual("<FXF={APPEND,EXCLUSIVE,READ,TEXT}>", repr(flag))



class OrderedConstantsTests(TestCase):
    """
    Tests for the ordering of constants.  All constants are ordered by
    the order in which they are defined in their container class.
    The ordering of constants that are not in the same container is not
    defined.
    """
    def test_orderedNameConstants_lt(self):
        """
        L{twisted.python.constants.NamedConstant} preserves definition
        order in C{<} comparisons.
        """
        self.assertTrue(NamedLetters.alpha < NamedLetters.beta)


    def test_orderedNameConstants_le(self):
        """
        L{twisted.python.constants.NamedConstant} preserves definition
        order in C{<=} comparisons.
        """
        self.assertTrue(NamedLetters.alpha <= NamedLetters.alpha)
        self.assertTrue(NamedLetters.alpha <= NamedLetters.beta)


    def test_orderedNameConstants_gt(self):
        """
        L{twisted.python.constants.NamedConstant} preserves definition
        order in C{>} comparisons.
        """
        self.assertTrue(NamedLetters.beta > NamedLetters.alpha)


    def test_orderedNameConstants_ge(self):
        """
        L{twisted.python.constants.NamedConstant} preserves definition
        order in C{>=} comparisons.
        """
        self.assertTrue(NamedLetters.alpha >= NamedLetters.alpha)
        self.assertTrue(NamedLetters.beta >= NamedLetters.alpha)


    def test_orderedValueConstants_lt(self):
        """
        L{twisted.python.constants.ValueConstant} preserves definition
        order in C{<} comparisons.
        """
        self.assertTrue(ValuedLetters.alpha < ValuedLetters.digamma)
        self.assertTrue(ValuedLetters.digamma < ValuedLetters.zeta)


    def test_orderedValueConstants_le(self):
        """
        L{twisted.python.constants.ValueConstant} preserves definition
        order in C{<=} comparisons.
        """
        self.assertTrue(ValuedLetters.alpha <= ValuedLetters.alpha)
        self.assertTrue(ValuedLetters.alpha <= ValuedLetters.digamma)
        self.assertTrue(ValuedLetters.digamma <= ValuedLetters.zeta)


    def test_orderedValueConstants_gt(self):
        """
        L{twisted.python.constants.ValueConstant} preserves definition
        order in C{>} comparisons.
        """
        self.assertTrue(ValuedLetters.digamma > ValuedLetters.alpha)
        self.assertTrue(ValuedLetters.zeta > ValuedLetters.digamma)


    def test_orderedValueConstants_ge(self):
        """
        L{twisted.python.constants.ValueConstant} preserves definition
        order in C{>=} comparisons.
        """
        self.assertTrue(ValuedLetters.alpha >= ValuedLetters.alpha)
        self.assertTrue(ValuedLetters.digamma >= ValuedLetters.alpha)
        self.assertTrue(ValuedLetters.zeta >= ValuedLetters.digamma)


    def test_orderedFlagConstants_lt(self):
        """
        L{twisted.python.constants.FlagConstant} preserves definition
        order in C{<} comparisons.
        """
        self.assertTrue(PizzaToppings.mozzarella < PizzaToppings.pesto)
        self.assertTrue(PizzaToppings.pesto < PizzaToppings.pepperoni)


    def test_orderedFlagConstants_le(self):
        """
        L{twisted.python.constants.FlagConstant} preserves definition
        order in C{<=} comparisons.
        """
        self.assertTrue(PizzaToppings.mozzarella <= PizzaToppings.mozzarella)
        self.assertTrue(PizzaToppings.mozzarella <= PizzaToppings.pesto)
        self.assertTrue(PizzaToppings.pesto <= PizzaToppings.pepperoni)


    def test_orderedFlagConstants_gt(self):
        """
        L{twisted.python.constants.FlagConstant} preserves definition
        order in C{>} comparisons.
        """
        self.assertTrue(PizzaToppings.pesto > PizzaToppings.mozzarella)
        self.assertTrue(PizzaToppings.pepperoni > PizzaToppings.pesto)


    def test_orderedFlagConstants_ge(self):
        """
        L{twisted.python.constants.FlagConstant} preserves definition
        order in C{>=} comparisons.
        """
        self.assertTrue(PizzaToppings.mozzarella >= PizzaToppings.mozzarella)
        self.assertTrue(PizzaToppings.pesto >= PizzaToppings.mozzarella)
        self.assertTrue(PizzaToppings.pepperoni >= PizzaToppings.pesto)


    def test_orderedDifferentConstants_lt(self):
        """
        L{twisted.python.constants._Constant.__lt__} returns C{NotImplemented}
        when comparing constants of different types.
        """
        self.assertEqual(
            NotImplemented,
            NamedLetters.alpha.__lt__(ValuedLetters.alpha)
        )


    def test_orderedDifferentConstants_le(self):
        """
        L{twisted.python.constants._Constant.__le__} returns C{NotImplemented}
        when comparing constants of different types.
        """
        self.assertEqual(
            NotImplemented,
            NamedLetters.alpha.__le__(ValuedLetters.alpha)
        )


    def test_orderedDifferentConstants_gt(self):
        """
        L{twisted.python.constants._Constant.__gt__} returns C{NotImplemented}
        when comparing constants of different types.
        """
        self.assertEqual(
            NotImplemented,
            NamedLetters.alpha.__gt__(ValuedLetters.alpha)
        )


    def test_orderedDifferentConstants_ge(self):
        """
        L{twisted.python.constants._Constant.__ge__} returns C{NotImplemented}
        when comparing constants of different types.
        """
        self.assertEqual(
            NotImplemented,
            NamedLetters.alpha.__ge__(ValuedLetters.alpha)
        )


    def test_orderedDifferentContainers_lt(self):
        """
        L{twisted.python.constants._Constant.__lt__} returns C{NotImplemented}
        when comparing constants belonging to different containers.
        """
        self.assertEqual(
            NotImplemented,
            NamedLetters.alpha.__lt__(MoreNamedLetters.digamma)
        )


    def test_orderedDifferentContainers_le(self):
        """
        L{twisted.python.constants._Constant.__le__} returns C{NotImplemented}
        when comparing constants belonging to different containers.
        """
        self.assertEqual(
            NotImplemented,
            NamedLetters.alpha.__le__(MoreNamedLetters.digamma)
        )


    def test_orderedDifferentContainers_gt(self):
        """
        L{twisted.python.constants._Constant.__gt__} returns C{NotImplemented}
        when comparing constants belonging to different containers.
        """
        self.assertEqual(
            NotImplemented,
            NamedLetters.alpha.__gt__(MoreNamedLetters.digamma)
        )


    def test_orderedDifferentContainers_ge(self):
        """
        L{twisted.python.constants._Constant.__ge__} returns C{NotImplemented}
        when comparing constants belonging to different containers.
        """
        self.assertEqual(
            NotImplemented,
            NamedLetters.alpha.__ge__(MoreNamedLetters.digamma)
        )



class NamedLetters(Names):
    """
    Some letters, named.
    """
    alpha = NamedConstant()
    beta  = NamedConstant()



class MoreNamedLetters(Names):
    """
    Some more letters, named.
    """
    digamma = NamedConstant()
    zeta  = NamedConstant()



class ValuedLetters(Values):
    """
    Some more letters, with cooresponding unicode values.
    """
    # Note u'\u0391' < u'\u03dc' > u'\u0396'.  We are ensuring here that the
    # definition is order different from the order of the values, which lets us
    # test that we're not somehow ordering by value and happen the get the same
    # results.
    alpha   = ValueConstant(u'\u0391')
    digamma = ValueConstant(u'\u03dc')
    zeta    = ValueConstant(u'\u0396')



class PizzaToppings(Flags):
    """
    Some pizza toppings, with obviously meaningful bitwise values.
    """
    # Note 1<<1 < 1<<4 > 1<<2, so we are ensuring here that the definition
    # order is different from the order of the values, which lets us test that
    # we're not somehow ordering by value and happen the get the same results.
    mozzarella = FlagConstant(1 << 1)
    pesto      = FlagConstant(1 << 4)
    pepperoni  = FlagConstant(1 << 2)

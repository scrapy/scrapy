# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for assertions provided by C{SynchronousTestCase} and C{TestCase},
provided by L{twisted.trial.unittest}.

L{TestFailureTests} demonstrates that L{SynchronousTestCase.fail} works, so that
is the only method on C{twisted.trial.unittest.SynchronousTestCase} that is
initially assumed to work.  The test classes are arranged so that the methods
demonstrated to work earlier in the file are used by those later in the file
(even though the runner will probably not run the tests in this order).
"""


import unittest as pyunit
import warnings

from incremental import Version, getVersionString

from twisted.internet.defer import Deferred, fail, succeed
from twisted.python.deprecate import deprecated, deprecatedModuleAttribute
from twisted.python.failure import Failure
from twisted.python.reflect import (
    accumulateMethods,
    fullyQualifiedName,
    prefixedMethods,
)
from twisted.python.util import FancyEqMixin
from twisted.trial import unittest


class MockEquality(FancyEqMixin):
    compareAttributes = ("name",)

    def __init__(self, name):
        self.name = name

    def __repr__(self) -> str:
        return f"MockEquality({self.name})"


class ComparisonError:
    """
    An object which raises exceptions from its comparison methods.
    """

    def _error(self, other):
        raise ValueError("Comparison is broken")

    __eq__ = _error
    __ne__ = _error


class TestFailureTests(pyunit.TestCase):
    """
    Tests for the most basic functionality of L{SynchronousTestCase}, for
    failing tests.

    This class contains tests to demonstrate that L{SynchronousTestCase.fail}
    can be used to fail a test, and that that failure is reflected in the test
    result object.  This should be sufficient functionality so that further
    tests can be built on L{SynchronousTestCase} instead of
    L{unittest.TestCase}.  This depends on L{unittest.TestCase} working.
    """

    class FailingTest(unittest.SynchronousTestCase):
        def test_fails(self):
            self.fail("This test fails.")

    def setUp(self):
        """
        Load a suite of one test which can be used to exercise the failure
        handling behavior.
        """
        components = [__name__, self.__class__.__name__, self.FailingTest.__name__]
        self.loader = pyunit.TestLoader()
        self.suite = self.loader.loadTestsFromName(".".join(components))
        self.test = list(self.suite)[0]

    def test_fail(self):
        """
        L{SynchronousTestCase.fail} raises
        L{SynchronousTestCase.failureException} with the given argument.
        """
        try:
            self.test.fail("failed")
        except self.test.failureException as result:
            self.assertEqual("failed", str(result))
        else:
            self.fail(
                "SynchronousTestCase.fail method did not raise "
                "SynchronousTestCase.failureException"
            )

    def test_failingExceptionFails(self):
        """
        When a test method raises L{SynchronousTestCase.failureException}, the test is
        marked as having failed on the L{TestResult}.
        """
        result = pyunit.TestResult()
        self.suite.run(result)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0][0], self.test)


class AssertFalseTests(unittest.SynchronousTestCase):
    """
    Tests for L{SynchronousTestCase}'s C{assertFalse} and C{failIf} assertion
    methods.

    This is pretty paranoid.  Still, a certain paranoia is healthy if you
    are testing a unit testing framework.

    @note: As of 11.2, C{assertFalse} is preferred over C{failIf}.
    """

    def _assertFalseFalse(self, method):
        """
        Perform the positive case test for C{failIf} or C{assertFalse}.

        @param method: The test method to test.
        """
        for notTrue in [0, 0.0, False, None, (), []]:
            result = method(notTrue, f"failed on {notTrue!r}")
            if result != notTrue:
                self.fail(f"Did not return argument {notTrue!r}")

    def _assertFalseTrue(self, method):
        """
        Perform the negative case test for C{failIf} or C{assertFalse}.

        @param method: The test method to test.
        """
        for true in [1, True, "cat", [1, 2], (3, 4)]:
            try:
                method(true, f"failed on {true!r}")
            except self.failureException as e:
                self.assertIn(
                    f"failed on {true!r}",
                    str(e),
                    f"Raised incorrect exception on {true!r}: {e!r}",
                )
            else:
                self.fail(
                    "Call to %s(%r) didn't fail"
                    % (
                        method.__name__,
                        true,
                    )
                )

    def test_failIfFalse(self):
        """
        L{SynchronousTestCase.failIf} returns its argument if its argument is
        not considered true.
        """
        self._assertFalseFalse(self.failIf)

    def test_assertFalseFalse(self):
        """
        L{SynchronousTestCase.assertFalse} returns its argument if its argument
        is not considered true.
        """
        self._assertFalseFalse(self.assertFalse)

    def test_failIfTrue(self):
        """
        L{SynchronousTestCase.failIf} raises
        L{SynchronousTestCase.failureException} if its argument is considered
        true.
        """
        self._assertFalseTrue(self.failIf)

    def test_assertFalseTrue(self):
        """
        L{SynchronousTestCase.assertFalse} raises
        L{SynchronousTestCase.failureException} if its argument is considered
        true.
        """
        self._assertFalseTrue(self.assertFalse)


class AssertTrueTests(unittest.SynchronousTestCase):
    """
    Tests for L{SynchronousTestCase}'s C{assertTrue} and C{failUnless} assertion
    methods.

    This is pretty paranoid.  Still, a certain paranoia is healthy if you
    are testing a unit testing framework.

    @note: As of 11.2, C{assertTrue} is preferred over C{failUnless}.
    """

    def _assertTrueFalse(self, method):
        """
        Perform the negative case test for C{assertTrue} and C{failUnless}.

        @param method: The test method to test.
        """
        for notTrue in [0, 0.0, False, None, (), []]:
            try:
                method(notTrue, f"failed on {notTrue!r}")
            except self.failureException as e:
                self.assertIn(
                    f"failed on {notTrue!r}",
                    str(e),
                    f"Raised incorrect exception on {notTrue!r}: {e!r}",
                )
            else:
                self.fail(
                    "Call to %s(%r) didn't fail"
                    % (
                        method.__name__,
                        notTrue,
                    )
                )

    def _assertTrueTrue(self, method):
        """
        Perform the positive case test for C{assertTrue} and C{failUnless}.

        @param method: The test method to test.
        """
        for true in [1, True, "cat", [1, 2], (3, 4)]:
            result = method(true, f"failed on {true!r}")
            if result != true:
                self.fail(f"Did not return argument {true!r}")

    def test_assertTrueFalse(self):
        """
        L{SynchronousTestCase.assertTrue} raises
        L{SynchronousTestCase.failureException} if its argument is not
        considered true.
        """
        self._assertTrueFalse(self.assertTrue)

    def test_failUnlessFalse(self):
        """
        L{SynchronousTestCase.failUnless} raises
        L{SynchronousTestCase.failureException} if its argument is not
        considered true.
        """
        self._assertTrueFalse(self.failUnless)

    def test_assertTrueTrue(self):
        """
        L{SynchronousTestCase.assertTrue} returns its argument if its argument
        is considered true.
        """
        self._assertTrueTrue(self.assertTrue)

    def test_failUnlessTrue(self):
        """
        L{SynchronousTestCase.failUnless} returns its argument if its argument
        is considered true.
        """
        self._assertTrueTrue(self.failUnless)


class SynchronousAssertionsTests(unittest.SynchronousTestCase):
    """
    Tests for L{SynchronousTestCase}'s assertion methods.  That is, failUnless*,
    failIf*, assert* (not covered by other more specific test classes).

    Note: As of 11.2, assertEqual is preferred over the failUnlessEqual(s)
    variants.  Tests have been modified to reflect this preference.

    This is pretty paranoid.  Still, a certain paranoia is healthy if you are
    testing a unit testing framework.
    """

    def _testEqualPair(self, first, second):
        x = self.assertEqual(first, second)
        if x != first:
            self.fail("assertEqual should return first parameter")

    def _testUnequalPair(self, first, second):
        """
        Assert that when called with unequal arguments, C{assertEqual} raises a
        failure exception with the same message as the standard library
        C{assertEqual} would have raised.
        """
        raised = False
        try:
            self.assertEqual(first, second)
        except self.failureException as ourFailure:
            case = pyunit.TestCase("setUp")
            try:
                case.assertEqual(first, second)
            except case.failureException as theirFailure:
                raised = True
                got = str(ourFailure)
                expected = str(theirFailure)
                if expected != got:
                    self.fail(f"Expected: {expected!r}; Got: {got!r}")

        if not raised:
            self.fail(f"Call to assertEqual({first!r}, {second!r}) didn't fail")

    def test_assertEqual_basic(self):
        self._testEqualPair("cat", "cat")
        self._testUnequalPair("cat", "dog")
        self._testEqualPair([1], [1])
        self._testUnequalPair([1], "orange")

    def test_assertEqual_custom(self):
        x = MockEquality("first")
        y = MockEquality("second")
        z = MockEquality("first")
        self._testEqualPair(x, x)
        self._testEqualPair(x, z)
        self._testUnequalPair(x, y)
        self._testUnequalPair(y, z)

    def test_assertEqualMessage(self):
        """
        When a message is passed to L{assertEqual} it is included in the error
        message.
        """
        message = "message"
        exception = self.assertRaises(
            self.failureException, self.assertEqual, "foo", "bar", message
        )
        self.assertIn(message, str(exception))

    def test_assertEqualNoneMessage(self):
        """
        If a message is specified as L{None}, it is not included in the error
        message of L{assertEqual}.
        """
        exceptionForNone = self.assertRaises(
            self.failureException, self.assertEqual, "foo", "bar", None
        )
        exceptionWithout = self.assertRaises(
            self.failureException, self.assertEqual, "foo", "bar"
        )
        self.assertEqual(str(exceptionWithout), str(exceptionForNone))

    def test_assertEqual_incomparable(self):
        apple = ComparisonError()
        orange = ["orange"]
        try:
            self.assertEqual(apple, orange)
        except self.failureException:
            self.fail("Fail raised when ValueError ought to have been raised.")
        except ValueError:
            # good. error not swallowed
            pass
        else:
            self.fail(
                "Comparing {!r} and {!r} should have raised an exception".format(
                    apple, orange
                )
            )

    def _raiseError(self, error):
        raise error

    def test_failUnlessRaises_expected(self):
        x = self.failUnlessRaises(ValueError, self._raiseError, ValueError)
        self.assertTrue(
            isinstance(x, ValueError),
            "Expect failUnlessRaises to return instance of raised " "exception.",
        )

    def test_failUnlessRaises_unexpected(self):
        try:
            self.failUnlessRaises(ValueError, self._raiseError, TypeError)
        except TypeError:
            self.fail("failUnlessRaises shouldn't re-raise unexpected " "exceptions")
        except self.failureException:
            # what we expect
            pass
        else:
            self.fail("Expected exception wasn't raised. Should have failed")

    def test_failUnlessRaises_noException(self):
        returnValue = 3
        try:
            self.failUnlessRaises(ValueError, lambda: returnValue)
        except self.failureException as e:
            self.assertEqual(str(e), "ValueError not raised (3 returned)")
        else:
            self.fail("Exception not raised. Should have failed")

    def test_failUnlessRaises_failureException(self):
        x = self.failUnlessRaises(
            self.failureException, self._raiseError, self.failureException
        )
        self.assertTrue(
            isinstance(x, self.failureException),
            f"Expected {self.failureException!r} instance to be returned",
        )
        try:
            x = self.failUnlessRaises(
                self.failureException, self._raiseError, ValueError
            )
        except self.failureException:
            # what we expect
            pass
        else:
            self.fail("Should have raised exception")

    def test_assertRaisesContextExpected(self):
        """
        If C{assertRaises} is used to create a context manager and an exception
        is raised from the body of the C{with} statement then the context
        manager's C{exception} attribute is set to the exception that was
        raised.
        """
        exception = ValueError("marker")

        with self.assertRaises(ValueError) as context:
            raise exception

        self.assertIs(exception, context.exception)

    def test_assertRaisesContextUnexpected(self):
        """
        If C{assertRaises} is used to create a context manager and the wrong
        exception type is raised from the body of the C{with} statement then
        the C{with} statement raises C{failureException} describing the
        mismatch.
        """
        try:
            with self.assertRaises(ValueError):
                raise TypeError("marker")
        except self.failureException as exception:
            message = str(exception)
            expected = ("{type} raised instead of ValueError:\n" " Traceback").format(
                type=fullyQualifiedName(TypeError)
            )
            self.assertTrue(
                message.startswith(expected),
                "Exception message did not begin with expected information: "
                "{}".format(message),
            )
        else:
            self.fail("Mismatched exception type should have caused test failure.")

    def test_assertRaisesContextNoException(self):
        """
        If C{assertRaises} is used to create a context manager and no exception
        is raised from the body of the C{with} statement then the C{with}
        statement raises C{failureException} describing the lack of exception.
        """
        try:
            with self.assertRaises(ValueError):
                # No exception is raised.
                pass
        except self.failureException as exception:
            message = str(exception)
            # `(None returned)` text is here for backward compatibility and should
            # be ignored for context manager use case.
            self.assertEqual(message, "ValueError not raised (None returned)")
        else:
            self.fail("Non-exception result should have caused test failure.")

    def test_brokenName(self):
        """
        If the exception type passed to C{assertRaises} does not have a
        C{__name__} then the context manager still manages to construct a
        descriptive string for it.
        """
        try:
            with self.assertRaises((ValueError, TypeError)):
                # Just some other kind of exception
                raise AttributeError()
        except self.failureException as exception:
            message = str(exception)
            valueError = "ValueError" not in message
            typeError = "TypeError" not in message
            errors = []
            if valueError:
                errors.append("expected ValueError in exception message")
            if typeError:
                errors.append("expected TypeError in exception message")
            if errors:
                self.fail("; ".join(errors), f"message = {message}")
        else:
            self.fail("Mismatched exception type should have caused test failure.")

    def test_failIfEqual_basic(self):
        x, y, z = [1], [2], [1]
        ret = self.failIfEqual(x, y)
        self.assertEqual(ret, x, "failIfEqual should return first parameter")
        self.failUnlessRaises(self.failureException, self.failIfEqual, x, x)
        self.failUnlessRaises(self.failureException, self.failIfEqual, x, z)

    def test_failIfEqual_customEq(self):
        x = MockEquality("first")
        y = MockEquality("second")
        z = MockEquality("fecund")
        ret = self.failIfEqual(x, y)
        self.assertEqual(ret, x, "failIfEqual should return first parameter")
        self.failUnlessRaises(self.failureException, self.failIfEqual, x, x)
        self.failIfEqual(x, z, "__ne__ should make these not equal")

    def test_failIfIdenticalPositive(self):
        """
        C{failIfIdentical} returns its first argument if its first and second
        arguments are not the same object.
        """
        x = object()
        y = object()
        result = self.failIfIdentical(x, y)
        self.assertEqual(x, result)

    def test_failIfIdenticalNegative(self):
        """
        C{failIfIdentical} raises C{failureException} if its first and second
        arguments are the same object.
        """
        x = object()
        self.failUnlessRaises(self.failureException, self.failIfIdentical, x, x)

    def test_failUnlessIdentical(self):
        x, y, z = [1], [1], [2]
        ret = self.failUnlessIdentical(x, x)
        self.assertEqual(ret, x, "failUnlessIdentical should return first " "parameter")
        self.failUnlessRaises(self.failureException, self.failUnlessIdentical, x, y)
        self.failUnlessRaises(self.failureException, self.failUnlessIdentical, x, z)

    def test_failUnlessApproximates(self):
        x, y, z = 1.0, 1.1, 1.2
        self.failUnlessApproximates(x, x, 0.2)
        ret = self.failUnlessApproximates(x, y, 0.2)
        self.assertEqual(
            ret, x, "failUnlessApproximates should return " "first parameter"
        )
        self.failUnlessRaises(
            self.failureException, self.failUnlessApproximates, x, z, 0.1
        )
        self.failUnlessRaises(
            self.failureException, self.failUnlessApproximates, x, y, 0.1
        )

    def test_failUnlessAlmostEqual(self):
        precision = 5
        x = 8.000001
        y = 8.00001
        z = 8.000002
        self.failUnlessAlmostEqual(x, x, precision)
        ret = self.failUnlessAlmostEqual(x, z, precision)
        self.assertEqual(
            ret,
            x,
            "failUnlessAlmostEqual should return "
            "first parameter (%r, %r)" % (ret, x),
        )
        self.failUnlessRaises(
            self.failureException, self.failUnlessAlmostEqual, x, y, precision
        )

    def test_failIfAlmostEqual(self):
        precision = 5
        x = 8.000001
        y = 8.00001
        z = 8.000002
        ret = self.failIfAlmostEqual(x, y, precision)
        self.assertEqual(
            ret,
            x,
            "failIfAlmostEqual should return " "first parameter (%r, %r)" % (ret, x),
        )
        self.failUnlessRaises(
            self.failureException, self.failIfAlmostEqual, x, x, precision
        )
        self.failUnlessRaises(
            self.failureException, self.failIfAlmostEqual, x, z, precision
        )

    def test_failUnlessSubstring(self):
        x = "cat"
        y = "the dog sat"
        z = "the cat sat"
        self.failUnlessSubstring(x, x)
        ret = self.failUnlessSubstring(x, z)
        self.assertEqual(ret, x, "should return first parameter")
        self.failUnlessRaises(self.failureException, self.failUnlessSubstring, x, y)
        self.failUnlessRaises(self.failureException, self.failUnlessSubstring, z, x)

    def test_failIfSubstring(self):
        x = "cat"
        y = "the dog sat"
        z = "the cat sat"
        self.failIfSubstring(z, x)
        ret = self.failIfSubstring(x, y)
        self.assertEqual(ret, x, "should return first parameter")
        self.failUnlessRaises(self.failureException, self.failIfSubstring, x, x)
        self.failUnlessRaises(self.failureException, self.failIfSubstring, x, z)

    def test_assertIs(self):
        """
        L{assertIs} passes if two objects are identical.
        """
        a = MockEquality("first")
        self.assertIs(a, a)

    def test_assertIsError(self):
        """
        L{assertIs} fails if two objects are not identical.
        """
        a, b = MockEquality("first"), MockEquality("first")
        self.assertEqual(a, b)
        self.assertRaises(self.failureException, self.assertIs, a, b)

    def test_assertIsNot(self):
        """
        L{assertIsNot} passes if two objects are not identical.
        """
        a, b = MockEquality("first"), MockEquality("first")
        self.assertEqual(a, b)
        self.assertIsNot(a, b)

    def test_assertIsNotError(self):
        """
        L{assertIsNot} fails if two objects are identical.
        """
        a = MockEquality("first")
        self.assertRaises(self.failureException, self.assertIsNot, a, a)

    def test_assertIsInstance(self):
        """
        Test a true condition of assertIsInstance.
        """
        A = type("A", (object,), {})
        a = A()
        self.assertIsInstance(a, A)

    def test_assertIsInstanceMultipleClasses(self):
        """
        Test a true condition of assertIsInstance with multiple classes.
        """
        A = type("A", (object,), {})
        B = type("B", (object,), {})
        a = A()
        self.assertIsInstance(a, (A, B))

    def test_assertIsInstanceError(self):
        """
        Test an error with assertIsInstance.
        """
        A = type("A", (object,), {})
        B = type("B", (object,), {})
        a = A()
        self.assertRaises(self.failureException, self.assertIsInstance, a, B)

    def test_assertIsInstanceErrorMultipleClasses(self):
        """
        Test an error with assertIsInstance and multiple classes.
        """
        A = type("A", (object,), {})
        B = type("B", (object,), {})
        C = type("C", (object,), {})
        a = A()
        self.assertRaises(self.failureException, self.assertIsInstance, a, (B, C))

    def test_assertIsInstanceCustomMessage(self):
        """
        If L{TestCase.assertIsInstance} is passed a custom message as its 3rd
        argument, the message is included in the failure exception raised when
        the assertion fails.
        """
        exc = self.assertRaises(
            self.failureException, self.assertIsInstance, 3, str, "Silly assertion"
        )
        self.assertIn("Silly assertion", str(exc))

    def test_assertNotIsInstance(self):
        """
        Test a true condition of assertNotIsInstance.
        """
        A = type("A", (object,), {})
        B = type("B", (object,), {})
        a = A()
        self.assertNotIsInstance(a, B)

    def test_assertNotIsInstanceMultipleClasses(self):
        """
        Test a true condition of assertNotIsInstance and multiple classes.
        """
        A = type("A", (object,), {})
        B = type("B", (object,), {})
        C = type("C", (object,), {})
        a = A()
        self.assertNotIsInstance(a, (B, C))

    def test_assertNotIsInstanceError(self):
        """
        Test an error with assertNotIsInstance.
        """
        A = type("A", (object,), {})
        a = A()
        error = self.assertRaises(self.failureException, self.assertNotIsInstance, a, A)
        self.assertEqual(str(error), f"{a!r} is an instance of {A}")

    def test_assertNotIsInstanceErrorMultipleClasses(self):
        """
        Test an error with assertNotIsInstance and multiple classes.
        """
        A = type("A", (object,), {})
        B = type("B", (object,), {})
        a = A()
        self.assertRaises(self.failureException, self.assertNotIsInstance, a, (A, B))

    def test_assertDictEqual(self):
        """
        L{twisted.trial.unittest.TestCase} supports the C{assertDictEqual}
        method inherited from the standard library in Python 2.7.
        """
        self.assertDictEqual({"a": 1}, {"a": 1})

    if getattr(unittest.SynchronousTestCase, "assertDictEqual", None) is None:
        test_assertDictEqual.skip = (  # type: ignore[attr-defined]
            "assertDictEqual is not available on this version of Python"
        )


class WarningAssertionTests(unittest.SynchronousTestCase):
    def test_assertWarns(self):
        """
        Test basic assertWarns report.
        """

        def deprecated(a):
            warnings.warn("Woo deprecated", category=DeprecationWarning)
            return a

        r = self.assertWarns(
            DeprecationWarning, "Woo deprecated", __file__, deprecated, 123
        )
        self.assertEqual(r, 123)

    def test_assertWarnsRegistryClean(self):
        """
        Test that assertWarns cleans the warning registry, so the warning is
        not swallowed the second time.
        """

        def deprecated(a):
            warnings.warn("Woo deprecated", category=DeprecationWarning)
            return a

        r1 = self.assertWarns(
            DeprecationWarning, "Woo deprecated", __file__, deprecated, 123
        )
        self.assertEqual(r1, 123)
        # The warning should be raised again
        r2 = self.assertWarns(
            DeprecationWarning, "Woo deprecated", __file__, deprecated, 321
        )
        self.assertEqual(r2, 321)

    def test_assertWarnsError(self):
        """
        Test assertWarns failure when no warning is generated.
        """

        def normal(a):
            return a

        self.assertRaises(
            self.failureException,
            self.assertWarns,
            DeprecationWarning,
            "Woo deprecated",
            __file__,
            normal,
            123,
        )

    def test_assertWarnsWrongCategory(self):
        """
        Test assertWarns failure when the category is wrong.
        """

        def deprecated(a):
            warnings.warn("Foo deprecated", category=DeprecationWarning)
            return a

        self.assertRaises(
            self.failureException,
            self.assertWarns,
            UserWarning,
            "Foo deprecated",
            __file__,
            deprecated,
            123,
        )

    def test_assertWarnsWrongMessage(self):
        """
        Test assertWarns failure when the message is wrong.
        """

        def deprecated(a):
            warnings.warn("Foo deprecated", category=DeprecationWarning)
            return a

        self.assertRaises(
            self.failureException,
            self.assertWarns,
            DeprecationWarning,
            "Bar deprecated",
            __file__,
            deprecated,
            123,
        )

    def test_assertWarnsWrongFile(self):
        """
        If the warning emitted by a function refers to a different file than is
        passed to C{assertWarns}, C{failureException} is raised.
        """

        def deprecated(a):
            # stacklevel=2 points at the direct caller of the function.  The
            # way assertRaises is invoked below, the direct caller will be
            # something somewhere in trial, not something in this file.  In
            # Python 2.5 and earlier, stacklevel of 0 resulted in a warning
            # pointing to the warnings module itself.  Starting in Python 2.6,
            # stacklevel of 0 and 1 both result in a warning pointing to *this*
            # file, presumably due to the fact that the warn function is
            # implemented in C and has no convenient Python
            # filename/linenumber.
            warnings.warn("Foo deprecated", category=DeprecationWarning, stacklevel=2)

        self.assertRaises(
            self.failureException,
            # Since the direct caller isn't in this file, try to assert that
            # the warning *does* point to this file, so that assertWarns raises
            # an exception.
            self.assertWarns,
            DeprecationWarning,
            "Foo deprecated",
            __file__,
            deprecated,
            123,
        )

    def test_assertWarnsOnClass(self):
        """
        Test assertWarns works when creating a class instance.
        """

        class Warn:
            def __init__(self):
                warnings.warn("Do not call me", category=RuntimeWarning)

        r = self.assertWarns(RuntimeWarning, "Do not call me", __file__, Warn)
        self.assertTrue(isinstance(r, Warn))
        r = self.assertWarns(RuntimeWarning, "Do not call me", __file__, Warn)
        self.assertTrue(isinstance(r, Warn))

    def test_assertWarnsOnMethod(self):
        """
        Test assertWarns works when used on an instance method.
        """

        class Warn:
            def deprecated(self, a):
                warnings.warn("Bar deprecated", category=DeprecationWarning)
                return a

        w = Warn()
        r = self.assertWarns(
            DeprecationWarning, "Bar deprecated", __file__, w.deprecated, 321
        )
        self.assertEqual(r, 321)
        r = self.assertWarns(
            DeprecationWarning, "Bar deprecated", __file__, w.deprecated, 321
        )
        self.assertEqual(r, 321)

    def test_assertWarnsOnCall(self):
        """
        Test assertWarns works on instance with C{__call__} method.
        """

        class Warn:
            def __call__(self, a):
                warnings.warn("Egg deprecated", category=DeprecationWarning)
                return a

        w = Warn()
        r = self.assertWarns(DeprecationWarning, "Egg deprecated", __file__, w, 321)
        self.assertEqual(r, 321)
        r = self.assertWarns(DeprecationWarning, "Egg deprecated", __file__, w, 321)
        self.assertEqual(r, 321)

    def test_assertWarnsFilter(self):
        """
        Test assertWarns on a warning filtered by default.
        """

        def deprecated(a):
            warnings.warn("Woo deprecated", category=PendingDeprecationWarning)
            return a

        r = self.assertWarns(
            PendingDeprecationWarning, "Woo deprecated", __file__, deprecated, 123
        )
        self.assertEqual(r, 123)

    def test_assertWarnsMultipleWarnings(self):
        """
        C{assertWarns} does not raise an exception if the function it is passed
        triggers the same warning more than once.
        """

        def deprecated():
            warnings.warn("Woo deprecated", category=PendingDeprecationWarning)

        def f():
            deprecated()
            deprecated()

        self.assertWarns(PendingDeprecationWarning, "Woo deprecated", __file__, f)

    def test_assertWarnsDifferentWarnings(self):
        """
        For now, assertWarns is unable to handle multiple different warnings,
        so it should raise an exception if it's the case.
        """

        def deprecated(a):
            warnings.warn("Woo deprecated", category=DeprecationWarning)
            warnings.warn("Another one", category=PendingDeprecationWarning)

        e = self.assertRaises(
            self.failureException,
            self.assertWarns,
            DeprecationWarning,
            "Woo deprecated",
            __file__,
            deprecated,
            123,
        )
        self.assertEqual(str(e), "Can't handle different warnings")

    def test_assertWarnsAfterUnassertedWarning(self):
        """
        Warnings emitted before L{TestCase.assertWarns} is called do not get
        flushed and do not alter the behavior of L{TestCase.assertWarns}.
        """

        class TheWarning(Warning):
            pass

        def f(message):
            warnings.warn(message, category=TheWarning)

        f("foo")
        self.assertWarns(TheWarning, "bar", __file__, f, "bar")
        [warning] = self.flushWarnings([f])
        self.assertEqual(warning["message"], "foo")


class ResultOfAssertionsTests(unittest.SynchronousTestCase):
    """
    Tests for L{SynchronousTestCase.successResultOf},
    L{SynchronousTestCase.failureResultOf}, and
    L{SynchronousTestCase.assertNoResult}.
    """

    result = object()
    failure = Failure(Exception("Bad times"))

    def test_withoutResult(self):
        """
        L{SynchronousTestCase.successResultOf} raises
        L{SynchronousTestCase.failureException} when called with a L{Deferred}
        with no current result.
        """
        self.assertRaises(self.failureException, self.successResultOf, Deferred())

    def test_successResultOfWithFailure(self):
        """
        L{SynchronousTestCase.successResultOf} raises
        L{SynchronousTestCase.failureException} when called with a L{Deferred}
        with a failure result.
        """
        self.assertRaises(
            self.failureException, self.successResultOf, fail(self.failure)
        )

    def test_successResultOfWithFailureHasTraceback(self):
        """
        L{SynchronousTestCase.successResultOf} raises a
        L{SynchronousTestCase.failureException} that has the original failure
        traceback when called with a L{Deferred} with a failure result.
        """
        try:
            self.successResultOf(fail(self.failure))
        except self.failureException as e:
            self.assertIn(self.failure.getTraceback(), str(e))

    def test_failureResultOfWithoutResult(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a L{Deferred}
        with no current result.
        """
        self.assertRaises(self.failureException, self.failureResultOf, Deferred())

    def test_failureResultOfWithSuccess(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a L{Deferred}
        with a success result.
        """
        self.assertRaises(
            self.failureException, self.failureResultOf, succeed(self.result)
        )

    def test_failureResultOfWithWrongFailure(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a L{Deferred}
        that fails with an exception type that was not expected.
        """
        self.assertRaises(
            self.failureException, self.failureResultOf, fail(self.failure), KeyError
        )

    def test_failureResultOfWithWrongFailureOneExpectedFailure(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a L{Deferred}
        that fails with an exception type that was not expected, and the
        L{SynchronousTestCase.failureException} message contains the expected
        exception type.
        """
        try:
            self.failureResultOf(fail(self.failure), KeyError)
        except self.failureException as e:
            self.assertIn(
                "Failure of type ({}.{}) expected on".format(
                    KeyError.__module__, KeyError.__name__
                ),
                str(e),
            )

    def test_failureResultOfWithWrongFailureOneExpectedFailureHasTB(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a L{Deferred}
        that fails with an exception type that was not expected, and the
        L{SynchronousTestCase.failureException} message contains the original
        failure traceback.
        """
        try:
            self.failureResultOf(fail(self.failure), KeyError)
        except self.failureException as e:
            self.assertIn(self.failure.getTraceback(), str(e))

    def test_failureResultOfWithWrongFailureMultiExpectedFailures(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a L{Deferred}
        with an exception type that was not expected, and the
        L{SynchronousTestCase.failureException} message contains the expected
        exception types in the error message.
        """
        try:
            self.failureResultOf(fail(self.failure), KeyError, IOError)
        except self.failureException as e:
            self.assertIn(
                "Failure of type ({}.{} or {}.{}) expected on".format(
                    KeyError.__module__,
                    KeyError.__name__,
                    IOError.__module__,
                    IOError.__name__,
                ),
                str(e),
            )

    def test_failureResultOfWithWrongFailureMultiExpectedFailuresHasTB(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a L{Deferred}
        with an exception type that was not expected, and the
        L{SynchronousTestCase.failureException} message contains the original
        failure traceback in the error message.
        """
        try:
            self.failureResultOf(fail(self.failure), KeyError, IOError)
        except self.failureException as e:
            self.assertIn(self.failure.getTraceback(), str(e))

    def test_successResultOfWithSuccessResult(self):
        """
        When passed a L{Deferred} which currently has a result (ie,
        L{Deferred.addCallback} would cause the added callback to be called
        before C{addCallback} returns), L{SynchronousTestCase.successResultOf}
        returns that result.
        """
        self.assertIdentical(self.result, self.successResultOf(succeed(self.result)))

    def test_failureResultOfWithExpectedFailureResult(self):
        """
        When passed a L{Deferred} which currently has a L{Failure} result (ie,
        L{Deferred.addErrback} would cause the added errback to be called
        before C{addErrback} returns), L{SynchronousTestCase.failureResultOf}
        returns that L{Failure} if its contained exception type is expected.
        """
        self.assertIdentical(
            self.failure,
            self.failureResultOf(fail(self.failure), self.failure.type, KeyError),
        )

    def test_failureResultOfWithFailureResult(self):
        """
        When passed a L{Deferred} which currently has a L{Failure} result
        (ie, L{Deferred.addErrback} would cause the added errback to be called
        before C{addErrback} returns), L{SynchronousTestCase.failureResultOf}
        returns that L{Failure}.
        """
        self.assertIdentical(self.failure, self.failureResultOf(fail(self.failure)))

    def test_assertNoResultSuccess(self):
        """
        When passed a L{Deferred} which currently has a success result (see
        L{test_withSuccessResult}), L{SynchronousTestCase.assertNoResult}
        raises L{SynchronousTestCase.failureException}.
        """
        self.assertRaises(
            self.failureException, self.assertNoResult, succeed(self.result)
        )

    def test_assertNoResultFailure(self):
        """
        When passed a L{Deferred} which currently has a failure result (see
        L{test_withFailureResult}), L{SynchronousTestCase.assertNoResult}
        raises L{SynchronousTestCase.failureException}.
        """
        self.assertRaises(
            self.failureException, self.assertNoResult, fail(self.failure)
        )

    def test_assertNoResult(self):
        """
        When passed a L{Deferred} with no current result,
        L{SynchronousTestCase.assertNoResult} does not raise an exception.
        """
        self.assertNoResult(Deferred())

    def test_assertNoResultPropagatesSuccess(self):
        """
        When passed a L{Deferred} with no current result, which is then
        fired with a success result, L{SynchronousTestCase.assertNoResult}
        doesn't modify the result of the L{Deferred}.
        """
        d = Deferred()
        self.assertNoResult(d)
        d.callback(self.result)
        self.assertEqual(self.result, self.successResultOf(d))

    def test_assertNoResultPropagatesLaterFailure(self):
        """
        When passed a L{Deferred} with no current result, which is then
        fired with a L{Failure} result, L{SynchronousTestCase.assertNoResult}
        doesn't modify the result of the L{Deferred}.
        """
        d = Deferred()
        self.assertNoResult(d)
        d.errback(self.failure)
        self.assertEqual(self.failure, self.failureResultOf(d))

    def test_assertNoResultSwallowsImmediateFailure(self):
        """
        When passed a L{Deferred} which currently has a L{Failure} result,
        L{SynchronousTestCase.assertNoResult} changes the result of the
        L{Deferred} to a success.
        """
        d = fail(self.failure)
        try:
            self.assertNoResult(d)
        except self.failureException:
            pass
        self.assertEqual(None, self.successResultOf(d))


class ResultOfCoroutineAssertionsTests(unittest.SynchronousTestCase):
    """
    Tests for L{SynchronousTestCase.successResultOf},
    L{SynchronousTestCase.failureResultOf}, and
    L{SynchronousTestCase.assertNoResult} when given a coroutine.
    """

    result = object()
    exception = Exception("Bad times")
    failure = Failure(exception)

    async def successResult(self):
        return self.result

    async def noCurrentResult(self):
        await Deferred()

    async def raisesException(self, exception=None):
        if exception is None:
            exception = self.exception
        raise exception

    def test_withoutResult(self):
        """
        L{SynchronousTestCase.successResultOf} raises
        L{SynchronousTestCase.failureException} when called with a coroutine
        with no current result.
        """
        self.assertRaises(
            self.failureException, self.successResultOf, self.noCurrentResult()
        )

    def test_successResultOfWithException(self):
        """
        L{SynchronousTestCase.successResultOf} raises
        L{SynchronousTestCase.failureException} when called with a coroutine
        that raises an exception.
        """
        self.assertRaises(
            self.failureException, self.successResultOf, self.raisesException()
        )

    def test_successResultOfWithFailureHasTraceback(self):
        """
        L{SynchronousTestCase.successResultOf} raises a
        L{SynchronousTestCase.failureException} that has the original failure
        traceback when called with a coroutine with a failure result.
        """
        exception = Exception("Bad times")
        try:
            self.successResultOf(self.raisesException(exception))
        except self.failureException as e:
            self.assertIn("Success result expected on", str(e))
            self.assertIn("builtins.Exception: Bad times", str(e))

    def test_failureResultOfWithoutResult(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a coroutine
        with no current result.
        """
        self.assertRaises(
            self.failureException, self.failureResultOf, self.noCurrentResult()
        )

    def test_failureResultOfWithSuccess(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a coroutine
        with a success result.
        """
        self.assertRaises(
            self.failureException, self.failureResultOf, self.successResult()
        )

    def test_failureResultOfWithWrongFailure(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a coroutine
        that raises an exception that was not expected.
        """
        self.assertRaises(
            self.failureException,
            self.failureResultOf,
            self.raisesException(),
            KeyError,
        )

    def test_failureResultOfWithWrongExceptionOneExpectedException(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a coroutine
        that raises an exception with a failure type that was not expected, and
        the L{SynchronousTestCase.failureException} message contains the
        expected exception type.
        """
        try:
            self.failureResultOf(self.raisesException(), KeyError)
        except self.failureException as e:
            self.assertIn(
                "Failure of type ({}.{}) expected on".format(
                    KeyError.__module__, KeyError.__name__
                ),
                str(e),
            )

    def test_failureResultOfWithWrongExceptionOneExpectedExceptionHasTB(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a coroutine
        that raises an exception with a failure type that was not expected, and
        the L{SynchronousTestCase.failureException} message contains the
        original exception traceback.
        """
        exception = Exception("Bad times")
        try:
            self.failureResultOf(self.raisesException(exception), KeyError)
        except self.failureException as e:
            self.assertIn("Failure of type (builtins.KeyError) expected on", str(e))
            self.assertIn("builtins.Exception: Bad times", str(e))

    def test_failureResultOfWithWrongExceptionMultiExpectedExceptions(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a coroutine
        that raises an exception of a type that was not expected, and the
        L{SynchronousTestCase.failureException} message contains expected
        exception types in the error message.
        """
        try:
            self.failureResultOf(self.raisesException(), KeyError, IOError)
        except self.failureException as e:
            self.assertIn(
                "Failure of type ({}.{} or {}.{}) expected on".format(
                    KeyError.__module__,
                    KeyError.__name__,
                    IOError.__module__,
                    IOError.__name__,
                ),
                str(e),
            )

    def test_failureResultOfWithWrongExceptionMultiExpectedExceptionsHasTB(self):
        """
        L{SynchronousTestCase.failureResultOf} raises
        L{SynchronousTestCase.failureException} when called with a coroutine
        that raises an exception of a type that was not expected, and the
        L{SynchronousTestCase.failureException} message contains the original
        exception traceback in the error message.
        """
        exception = Exception("Bad times")

        try:
            self.failureResultOf(self.raisesException(exception), KeyError, IOError)
        except self.failureException as e:
            self.assertIn(
                "Failure of type (builtins.KeyError or builtins.OSError) expected on",
                str(e),
            )
            self.assertIn("builtins.Exception: Bad times", str(e))

    def test_successResultOfWithSuccessResult(self):
        """
        When passed a coroutine which currently has a result (ie, if converted
        into a L{Deferred}, L{Deferred.addCallback} would cause the added
        callback to be called before C{addCallback} returns),
        L{SynchronousTestCase.successResultOf} returns that result.
        """
        self.assertIdentical(self.result, self.successResultOf(self.successResult()))

    def test_failureResultOfWithExpectedException(self):
        """
        When passed a coroutine which currently has an exception result (ie, if
        converted into a L{Deferred}, L{Deferred.addErrback} would cause the
        added errback to be called before C{addErrback} returns),
        L{SynchronousTestCase.failureResultOf} returns a L{Failure} containing
        that exception, if the exception type is expected.
        """
        self.assertEqual(
            self.failure.value,
            self.failureResultOf(
                self.raisesException(), self.failure.type, KeyError
            ).value,
        )

    def test_failureResultOfWithException(self):
        """
        When passed a coroutine which currently has an exception result (ie, if
        converted into a L{Deferred}, L{Deferred.addErrback} would cause the
        added errback to be called before C{addErrback} returns),
        L{SynchronousTestCase.failureResultOf} returns returns a L{Failure}
        containing that exception.
        """
        self.assertEqual(
            self.failure.value, self.failureResultOf(self.raisesException()).value
        )

    def test_assertNoResultSuccess(self):
        """
        When passed a coroutine which currently has a success result (see
        L{test_withSuccessResult}), L{SynchronousTestCase.assertNoResult}
        raises L{SynchronousTestCase.failureException}.
        """
        self.assertRaises(
            self.failureException, self.assertNoResult, self.successResult()
        )

    def test_assertNoResultFailure(self):
        """
        When passed a coroutine which currently has an exception result (see
        L{test_withFailureResult}), L{SynchronousTestCase.assertNoResult}
        raises L{SynchronousTestCase.failureException}.
        """
        self.assertRaises(
            self.failureException, self.assertNoResult, self.raisesException()
        )

    def test_assertNoResult(self):
        """
        When passed a coroutine with no current result,
        L{SynchronousTestCase.assertNoResult} does not raise an exception.
        """
        self.assertNoResult(self.noCurrentResult())

    def test_assertNoResultPropagatesSuccess(self):
        """
        When passed a coroutine awaiting a L{Deferred} with no current result,
        which is then fired with a success result,
        L{SynchronousTestCase.assertNoResult} doesn't modify the result of the
        L{Deferred}.
        """
        d = Deferred()

        async def noCurrentResult():
            return await d

        c = noCurrentResult()
        self.assertNoResult(d)
        d.callback(self.result)
        self.assertEqual(self.result, self.successResultOf(c))

    def test_assertNoResultPropagatesLaterFailure(self):
        """
        When passed a coroutine awaiting a L{Deferred} with no current result,
        which is then fired with a L{Failure} result,
        L{SynchronousTestCase.assertNoResult} doesn't modify the result of the
        L{Deferred}.
        """
        f = Failure(self.exception)
        d = Deferred()

        async def noCurrentResult():
            return await d

        c = noCurrentResult()
        self.assertNoResult(d)
        d.errback(f)
        self.assertEqual(f.value, self.failureResultOf(c).value)

    def test_assertNoResultSwallowsImmediateFailure(self):
        """
        When passed a L{Deferred} which currently has a L{Failure} result,
        L{SynchronousTestCase.assertNoResult} changes the result of the
        L{Deferred} to a success.
        """
        d = fail(self.failure)

        async def raisesException():
            return await d

        c = raisesException()
        try:
            self.assertNoResult(d)
        except self.failureException:
            pass
        self.assertEqual(None, self.successResultOf(c))


class AssertionNamesTests(unittest.SynchronousTestCase):
    """
    Tests for consistency of naming within TestCase assertion methods
    """

    def _getAsserts(self):
        dct = {}
        accumulateMethods(self, dct, "assert")
        return [dct[k] for k in dct if not k.startswith("Not") and k != "_"]

    def _name(self, x):
        return x.__name__

    def test_failUnlessMatchesAssert(self):
        """
        The C{failUnless*} test methods are a subset of the C{assert*} test
        methods.  This is intended to ensure that methods using the
        I{failUnless} naming scheme are not added without corresponding methods
        using the I{assert} naming scheme.  The I{assert} naming scheme is
        preferred, and new I{assert}-prefixed methods may be added without
        corresponding I{failUnless}-prefixed methods.
        """
        asserts = set(self._getAsserts())
        failUnlesses = set(prefixedMethods(self, "failUnless"))
        self.assertEqual(failUnlesses, asserts.intersection(failUnlesses))

    def test_failIf_matches_assertNot(self):
        asserts = prefixedMethods(unittest.SynchronousTestCase, "assertNot")
        failIfs = prefixedMethods(unittest.SynchronousTestCase, "failIf")
        self.assertEqual(
            sorted(asserts, key=self._name), sorted(failIfs, key=self._name)
        )

    def test_equalSpelling(self):
        for name, value in vars(self).items():
            if not callable(value):
                continue
            if name.endswith("Equal"):
                self.assertTrue(hasattr(self, name + "s"), f"{name} but no {name}s")
                self.assertEqual(value, getattr(self, name + "s"))
            if name.endswith("Equals"):
                self.assertTrue(hasattr(self, name[:-1]), f"{name} but no {name[:-1]}")
                self.assertEqual(value, getattr(self, name[:-1]))


class CallDeprecatedTests(unittest.SynchronousTestCase):
    """
    Test use of the L{SynchronousTestCase.callDeprecated} method with version objects.
    """

    version = Version("Twisted", 8, 0, 0)

    def test_callDeprecatedSuppressesWarning(self):
        """
        callDeprecated calls a deprecated callable, suppressing the
        deprecation warning.
        """
        self.callDeprecated(self.version, oldMethod, "foo")
        self.assertEqual(self.flushWarnings(), [], "No warnings should be shown")

    def test_callDeprecatedCallsFunction(self):
        """
        L{callDeprecated} actually calls the callable passed to it, and
        forwards the result.
        """
        result = self.callDeprecated(self.version, oldMethod, "foo")
        self.assertEqual("foo", result)

    def test_failsWithoutDeprecation(self):
        """
        L{callDeprecated} raises a test failure if the callable is not
        deprecated.
        """

        def notDeprecated():
            pass

        exception = self.assertRaises(
            self.failureException, self.callDeprecated, self.version, notDeprecated
        )
        self.assertEqual("%r is not deprecated." % notDeprecated, str(exception))

    def test_failsWithIncorrectDeprecation(self):
        """
        callDeprecated raises a test failure if the callable was deprecated
        at a different version to the one expected.
        """
        differentVersion = Version("Foo", 1, 2, 3)
        exception = self.assertRaises(
            self.failureException,
            self.callDeprecated,
            differentVersion,
            oldMethod,
            "foo",
        )
        self.assertIn(getVersionString(self.version), str(exception))
        self.assertIn(getVersionString(differentVersion), str(exception))

    def test_nestedDeprecation(self):
        """
        L{callDeprecated} ignores all deprecations apart from the first.

        Multiple warnings are generated when a deprecated function calls
        another deprecated function. The first warning is the one generated by
        the explicitly called function. That's the warning that we care about.
        """
        differentVersion = Version("Foo", 1, 2, 3)

        def nestedDeprecation(*args):
            return oldMethod(*args)

        nestedDeprecation = deprecated(differentVersion)(nestedDeprecation)

        self.callDeprecated(differentVersion, nestedDeprecation, 24)

        # The oldMethod deprecation should have been emitted too, not captured
        # by callDeprecated.  Flush it now to make sure it did happen and to
        # prevent it from showing up on stdout.
        warningsShown = self.flushWarnings()
        self.assertEqual(len(warningsShown), 1, f"Unexpected warnings: {warningsShown}")

    def test_callDeprecationWithMessage(self):
        """
        L{callDeprecated} can take a message argument used to check the warning
        emitted.
        """
        self.callDeprecated((self.version, "newMethod"), oldMethodReplaced, 1)

    def test_callDeprecationWithWrongMessage(self):
        """
        If the message passed to L{callDeprecated} doesn't match,
        L{callDeprecated} raises a test failure.
        """
        exception = self.assertRaises(
            self.failureException,
            self.callDeprecated,
            (self.version, "something.wrong"),
            oldMethodReplaced,
            1,
        )
        self.assertIn(getVersionString(self.version), str(exception))
        self.assertIn("please use newMethod instead", str(exception))


@deprecated(CallDeprecatedTests.version)
def oldMethod(x):
    """
    Deprecated method for testing.
    """
    return x


@deprecated(CallDeprecatedTests.version, replacement="newMethod")
def oldMethodReplaced(x):
    """
    Another deprecated method, which has been deprecated in favor of the
    mythical 'newMethod'.
    """
    return 2 * x


class GetDeprecatedModuleAttributeTests(unittest.SynchronousTestCase):
    """
    Test L{SynchronousTestCase.getDeprecatedModuleAttribute}

    @ivar version: The version at which L{test_assertions.somethingOld}
        is marked deprecated.
    @type version: L{incremental.Version}
    """

    version = Version("Bar", 1, 2, 3)

    def test_deprecated(self):
        """
        L{getDeprecatedModuleAttribute} returns the specified attribute and
        consumes the deprecation warning that generates.
        """
        self.assertIs(
            _somethingOld,
            self.getDeprecatedModuleAttribute(
                __name__,
                "somethingOld",
                self.version,
            ),
        )
        self.assertEqual([], self.flushWarnings())

    def test_message(self):
        """
        The I{message} argument to L{getDeprecatedModuleAttribute} matches the
        prefix of the deprecation message.
        """
        self.assertIs(
            _somethingOld,
            self.getDeprecatedModuleAttribute(
                __name__,
                "somethingOld",
                self.version,
                message="It's old",
            ),
        )
        self.assertEqual([], self.flushWarnings())

    def test_messageMismatch(self):
        """
        L{getDeprecatedModuleAttribute} fails the test if the I{message} isn't
        part of the deprecation message prefix.
        """
        self.assertRaises(
            self.failureException,
            self.getDeprecatedModuleAttribute,
            __name__,
            "somethingOld",
            self.version,
            "It's shiny and new",  # Doesn't match.
        )
        self.assertEqual([], self.flushWarnings())

    def test_notDeprecated(self):
        """
        L{getDeprecatedModuleAttribute} fails the test when used to get an
        attribute that isn't actually deprecated.
        """
        self.assertRaises(
            self.failureException,
            self.getDeprecatedModuleAttribute,
            __name__,
            "somethingNew",
            self.version,
        )


def somethingOld():
    """
    A deprecated module attribute. Used by
    L{GetDeprecatedModuleAttributeTests.test_deprecated}.
    """


# A non-deprecated alias of _somethingOld.
_somethingOld = somethingOld


deprecatedModuleAttribute(
    GetDeprecatedModuleAttributeTests.version,
    "It's old and clunky",
    __name__,
    "somethingOld",
)


def somethingNew():
    """
    A module attribute that is not deprecated. Used by
    L{GetDeprecatedModuleAttributeTests.test_notDeprecated}.
    """

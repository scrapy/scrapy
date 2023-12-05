# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Interfaces for Trial.

Maintainer: Jonathan Lange
"""


import zope.interface as zi


class ITestCase(zi.Interface):
    """
    The interface that a test case must implement in order to be used in Trial.
    """

    failureException = zi.Attribute(
        "The exception class that is raised by failed assertions"
    )

    def __call__(result):
        """
        Run the test. Should always do exactly the same thing as run().
        """

    def countTestCases():
        """
        Return the number of tests in this test case. Usually 1.
        """

    def id():
        """
        Return a unique identifier for the test, usually the fully-qualified
        Python name.
        """

    def run(result):
        """
        Run the test, storing the results in C{result}.

        @param result: A L{TestResult}.
        """

    def shortDescription():
        """
        Return a short description of the test.
        """


class IReporter(zi.Interface):
    """
    I report results from a run of a test suite.
    """

    shouldStop = zi.Attribute(
        "A boolean indicating that this reporter would like the " "test run to stop."
    )
    testsRun = zi.Attribute(
        """
        The number of tests that seem to have been run according to this
        reporter.
        """
    )

    def startTest(method):
        """
        Report the beginning of a run of a single test method.

        @param method: an object that is adaptable to ITestMethod
        """

    def stopTest(method):
        """
        Report the status of a single test method

        @param method: an object that is adaptable to ITestMethod
        """

    def addSuccess(test):
        """
        Record that test passed.
        """

    def addError(test, error):
        """
        Record that a test has raised an unexpected exception.

        @param test: The test that has raised an error.
        @param error: The error that the test raised. It will either be a
            three-tuple in the style of C{sys.exc_info()} or a
            L{Failure<twisted.python.failure.Failure>} object.
        """

    def addFailure(test, failure):
        """
        Record that a test has failed with the given failure.

        @param test: The test that has failed.
        @param failure: The failure that the test failed with. It will
            either be a three-tuple in the style of C{sys.exc_info()}
            or a L{Failure<twisted.python.failure.Failure>} object.
        """

    def addExpectedFailure(test, failure, todo=None):
        """
        Record that the given test failed, and was expected to do so.

        In Twisted 15.5 and prior, C{todo} was a mandatory parameter.

        @type test: L{unittest.TestCase}
        @param test: The test which this is about.
        @type failure: L{failure.Failure}
        @param failure: The error which this test failed with.
        @type todo: L{unittest.Todo}
        @param todo: The reason for the test's TODO status. If L{None}, a
            generic reason is used.
        """

    def addUnexpectedSuccess(test, todo=None):
        """
        Record that the given test failed, and was expected to do so.

        In Twisted 15.5 and prior, C{todo} was a mandatory parameter.

        @type test: L{unittest.TestCase}
        @param test: The test which this is about.
        @type todo: L{unittest.Todo}
        @param todo: The reason for the test's TODO status. If L{None}, a
            generic reason is used.
        """

    def addSkip(test, reason):
        """
        Record that a test has been skipped for the given reason.

        @param test: The test that has been skipped.
        @param reason: An object that the test case has specified as the reason
            for skipping the test.
        """

    def wasSuccessful():
        """
        Return a boolean indicating whether all test results that were reported
        to this reporter were successful or not.
        """

    def done():
        """
        Called when the test run is complete.

        This gives the result object an opportunity to display a summary of
        information to the user. Once you have called C{done} on an
        L{IReporter} object, you should assume that the L{IReporter} object is
        no longer usable.
        """

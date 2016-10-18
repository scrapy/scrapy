# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Interfaces for Trial.

Maintainer: Jonathan Lange
"""

from __future__ import division, absolute_import

import zope.interface as zi
from zope.interface import Attribute


class ITestCase(zi.Interface):
    """
    The interface that a test case must implement in order to be used in Trial.
    """

    failureException = zi.Attribute(
        "The exception class that is raised by failed assertions")


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

    stream = zi.Attribute(
        "Deprecated in Twisted 8.0. "
        "The io-stream that this reporter will write to")
    tbformat = zi.Attribute("Either 'default', 'brief', or 'verbose'")
    args = zi.Attribute(
        "Additional string argument passed from the command line")
    shouldStop = zi.Attribute(
        """
        A boolean indicating that this reporter would like the test run to stop.
        """)
    separator = Attribute(
        "Deprecated in Twisted 8.0. "
        "A value which will occasionally be passed to the L{write} method.")
    testsRun = Attribute(
        """
        The number of tests that seem to have been run according to this
        reporter.
        """)


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


    def startSuite(name):
        """
        Deprecated in Twisted 8.0.

        Suites which wish to appear in reporter output should call this
        before running their tests.
        """


    def endSuite(name):
        """
        Deprecated in Twisted 8.0.

        Called at the end of a suite, if and only if that suite has called
        C{startSuite}.
        """


    def cleanupErrors(errs):
        """
        Deprecated in Twisted 8.0.

        Called when the reactor has been left in a 'dirty' state

        @param errs: a list of L{twisted.python.failure.Failure}s
        """


    def upDownError(userMeth, warn=True, printStatus=True):
        """
        Deprecated in Twisted 8.0.

        Called when an error occurs in a setUp* or tearDown* method

        @param warn: indicates whether or not the reporter should emit a
                     warning about the error
        @type warn: Boolean
        @param printStatus: indicates whether or not the reporter should
                            print the name of the method and the status
                            message appropriate for the type of error
        @type printStatus: Boolean
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
        @type error: L{failure.Failure}
        @param error: The error which this test failed with.
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


    def printSummary():
        """
        Deprecated in Twisted 8.0, use L{done} instead.

        Present a summary of the test results.
        """


    def printErrors():
        """
        Deprecated in Twisted 8.0, use L{done} instead.

        Present the errors that have occurred during the test run. This method
        will be called after all tests have been run.
        """


    def write(string):
        """
        Deprecated in Twisted 8.0, use L{done} instead.

        Display a string to the user, without appending a new line.
        """


    def writeln(string):
        """
        Deprecated in Twisted 8.0, use L{done} instead.

        Display a string to the user, appending a new line.
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

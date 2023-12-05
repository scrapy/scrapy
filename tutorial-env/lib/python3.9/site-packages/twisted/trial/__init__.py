# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
#
# Maintainer: Jonathan Lange

"""
Twisted Trial: Asynchronous unit testing framework.

Trial extends Python's builtin C{unittest} to provide support for asynchronous
tests.

Trial strives to be compatible with other Python xUnit testing frameworks.
"Compatibility" is a difficult things to define. In practice, it means that:

 - L{twisted.trial.unittest.TestCase} objects should be able to be used by
   other test runners without those runners requiring special support for
   Trial tests.

 - Tests that subclass the standard library C{TestCase} and don't do anything
   "too weird" should be able to be discoverable and runnable by the Trial
   test runner without the authors of those tests having to jump through
   hoops.

 - Tests that implement the interface provided by the standard library
   C{TestCase} should be runnable by the Trial runner.

 - The Trial test runner and Trial L{unittest.TestCase} objects ought to be
   able to use standard library C{TestResult} objects, and third party
   C{TestResult} objects based on the standard library.

This list is not necessarily exhaustive -- compatibility is hard to define.
Contributors who discover more helpful ways of defining compatibility are
encouraged to update this document.


Examples:

B{Timeouts} for tests should be implemented in the runner. If this is done,
then timeouts could work for third-party TestCase objects as well as for
L{twisted.trial.unittest.TestCase} objects. Further, Twisted C{TestCase}
objects will run in other runners without timing out.
See U{http://twistedmatrix.com/trac/ticket/2675}.

Running tests in a temporary directory should be a feature of the test case,
because often tests themselves rely on this behaviour. If the feature is
implemented in the runner, then tests will change behaviour (possibly
breaking) when run in a different test runner. Further, many tests don't even
care about the filesystem.
See U{http://twistedmatrix.com/trac/ticket/2916}.
"""

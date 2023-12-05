# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.names} example scripts.
"""


import os
import sys
from io import StringIO

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SkipTest, TestCase


class ExampleTestBase:
    """
    This is a mixin which adds an example to the path, tests it, and then
    removes it from the path and unimports the modules which the test loaded.
    Test cases which test example code and documentation listings should use
    this.

    This is done this way so that examples can live in isolated path entries,
    next to the documentation, replete with their own plugin packages and
    whatever other metadata they need.  Also, example code is a rare instance
    of it being valid to have multiple versions of the same code in the
    repository at once, rather than relying on version control, because
    documentation will often show the progression of a single piece of code as
    features are added to it, and we want to test each one.
    """

    def setUp(self):
        """
        Add our example directory to the path and record which modules are
        currently loaded.
        """
        self.originalPath = sys.path[:]
        self.originalModules = sys.modules.copy()

        # Python usually expects native strs to be written to sys.stdout/stderr
        self.fakeErr = StringIO()
        self.patch(sys, "stderr", self.fakeErr)
        self.fakeOut = StringIO()
        self.patch(sys, "stdout", self.fakeOut)

        # Get documentation root
        try:
            here = FilePath(os.environ["TOX_INI_DIR"]).child("docs")
        except KeyError:
            raise SkipTest(
                "Examples not found ($TOX_INI_DIR unset) - cannot test",
            )

        # Find the example script within this branch
        for childName in self.exampleRelativePath.split("/"):
            here = here.child(childName)
            if not here.exists():
                raise SkipTest(f"Examples ({here.path}) not found - cannot test")
        self.examplePath = here

        # Add the example parent folder to the Python path
        sys.path.append(self.examplePath.parent().path)

        # Import the example as a module
        moduleName = self.examplePath.basename().split(".")[0]
        self.example = __import__(moduleName)

    def tearDown(self):
        """
        Remove the example directory from the path and remove all
        modules loaded by the test from sys.modules.
        """
        sys.modules.clear()
        sys.modules.update(self.originalModules)
        sys.path[:] = self.originalPath

    def test_shebang(self):
        """
        The example scripts start with the standard shebang line.
        """
        with self.examplePath.open() as f:
            self.assertEqual(f.readline().rstrip(), b"#!/usr/bin/env python")

    def test_usageConsistency(self):
        """
        The example script prints a usage message to stdout if it is
        passed a --help option and then exits.

        The first line should contain a USAGE summary, explaining the
        accepted command arguments.
        """
        # Pass None as first parameter - the reactor - it shouldn't
        # get as far as calling it.
        self.assertRaises(SystemExit, self.example.main, None, "--help")

        out = self.fakeOut.getvalue().splitlines()
        self.assertTrue(
            out[0].startswith("Usage:"),
            'Usage message first line should start with "Usage:". '
            "Actual: %r" % (out[0],),
        )

    def test_usageConsistencyOnError(self):
        """
        The example script prints a usage message to stderr if it is
        passed unrecognized command line arguments.

        The first line should contain a USAGE summary, explaining the
        accepted command arguments.

        The last line should contain an ERROR summary, explaining that
        incorrect arguments were supplied.
        """
        # Pass None as first parameter - the reactor - it shouldn't
        # get as far as calling it.
        self.assertRaises(SystemExit, self.example.main, None, "--unexpected_argument")

        err = self.fakeErr.getvalue().splitlines()
        self.assertTrue(
            err[0].startswith("Usage:"),
            'Usage message first line should start with "Usage:". '
            "Actual: %r" % (err[0],),
        )
        self.assertTrue(
            err[-1].startswith("ERROR:"),
            'Usage message last line should start with "ERROR:" '
            "Actual: %r" % (err[-1],),
        )


class TestDnsTests(ExampleTestBase, TestCase):
    """
    Test the testdns.py example script.
    """

    exampleRelativePath = "names/examples/testdns.py"


class GetHostByNameTests(ExampleTestBase, TestCase):
    """
    Test the gethostbyname.py example script.
    """

    exampleRelativePath = "names/examples/gethostbyname.py"


class DnsServiceTests(ExampleTestBase, TestCase):
    """
    Test the dns-service.py example script.
    """

    exampleRelativePath = "names/examples/dns-service.py"


class MultiReverseLookupTests(ExampleTestBase, TestCase):
    """
    Test the multi_reverse_lookup.py example script.
    """

    exampleRelativePath = "names/examples/multi_reverse_lookup.py"

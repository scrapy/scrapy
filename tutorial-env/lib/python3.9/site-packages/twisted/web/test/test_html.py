# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.trial import unittest
from twisted.web import html


class WebHtmlTests(unittest.TestCase):
    """
    Unit tests for L{twisted.web.html}.
    """

    def test_deprecation(self):
        """
        Calls to L{twisted.web.html} members emit a deprecation warning.
        """

        def assertDeprecationWarningOf(method):
            """
            Check that a deprecation warning is present.
            """
            warningsShown = self.flushWarnings([self.test_deprecation])
            self.assertEqual(len(warningsShown), 1)
            self.assertIdentical(warningsShown[0]["category"], DeprecationWarning)
            self.assertEqual(
                warningsShown[0]["message"],
                "twisted.web.html.%s was deprecated in Twisted 15.3.0; "
                "please use twisted.web.template instead" % (method,),
            )

        html.PRE("")
        assertDeprecationWarningOf("PRE")

        html.UL([])
        assertDeprecationWarningOf("UL")

        html.linkList([])
        assertDeprecationWarningOf("linkList")

        html.output(lambda: None)
        assertDeprecationWarningOf("output")

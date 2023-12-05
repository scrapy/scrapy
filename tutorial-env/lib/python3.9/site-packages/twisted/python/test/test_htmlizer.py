# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.htmlizer}.
"""

from io import BytesIO

from twisted.python.htmlizer import filter
from twisted.trial.unittest import TestCase


class FilterTests(TestCase):
    """
    Tests for L{twisted.python.htmlizer.filter}.
    """

    def test_empty(self):
        """
        If passed an empty input file, L{filter} writes a I{pre} tag containing
        only an end marker to the output file.
        """
        input = BytesIO(b"")
        output = BytesIO()
        filter(input, output)
        self.assertEqual(
            output.getvalue(), b'<pre><span class="py-src-endmarker"></span></pre>\n'
        )

    def test_variable(self):
        """
        If passed an input file containing a variable access, L{filter} writes
        a I{pre} tag containing a I{py-src-variable} span containing the
        variable.
        """
        input = BytesIO(b"foo\n")
        output = BytesIO()
        filter(input, output)
        self.assertEqual(
            output.getvalue(),
            b'<pre><span class="py-src-variable">foo</span>'
            b'<span class="py-src-newline">\n'
            b'</span><span class="py-src-endmarker"></span></pre>\n',
        )

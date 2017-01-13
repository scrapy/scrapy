# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet._pollingfile}.
"""

from twisted.python.runtime import platform
from twisted.trial.unittest import TestCase

if platform.isWindows():
    from twisted.internet import _pollingfile
else:
    _pollingfile = None



class PollableWritePipeTests(TestCase):
    """
    Tests for L{_pollingfile._PollableWritePipe}.
    """

    def test_writeUnicode(self):
        """
        L{_pollingfile._PollableWritePipe.write} raises a C{TypeError} if an
        attempt is made to append unicode data to the output buffer.
        """
        p = _pollingfile._PollableWritePipe(1, lambda: None)
        self.assertRaises(TypeError, p.write, u"test")


    def test_writeSequenceUnicode(self):
        """
        L{_pollingfile._PollableWritePipe.writeSequence} raises a C{TypeError}
        if unicode data is part of the data sequence to be appended to the
        output buffer.
        """
        p = _pollingfile._PollableWritePipe(1, lambda: None)
        self.assertRaises(TypeError, p.writeSequence, [u"test"])
        self.assertRaises(TypeError, p.writeSequence, (u"test", ))




if _pollingfile is None:
    PollableWritePipeTests.skip = "Test will run only on Windows."

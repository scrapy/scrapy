# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{inetdconf}.
"""

from twisted.runner import inetdconf
from twisted.trial import unittest


class ServicesConfTests(unittest.TestCase):
    """
    Tests for L{inetdconf.ServicesConf}
    """

    servicesFilename1 = None
    servicesFilename2 = None

    def setUp(self):
        self.servicesFilename1 = self.mktemp()
        with open(self.servicesFilename1, "w") as f:
            f.write(
                """
            # This is a comment
            http            80/tcp          www www-http    # WorldWideWeb HTTP
            http            80/udp          www www-http
            http            80/sctp
            """
            )
        self.servicesFilename2 = self.mktemp()
        with open(self.servicesFilename2, "w") as f:
            f.write(
                """
            https           443/tcp                # http protocol over TLS/SSL
            """
            )

    def test_parseDefaultFilename(self):
        """
        Services are parsed from default filename.
        """
        conf = inetdconf.ServicesConf()
        conf.defaultFilename = self.servicesFilename1
        conf.parseFile()
        self.assertEqual(
            conf.services,
            {
                ("http", "tcp"): 80,
                ("http", "udp"): 80,
                ("http", "sctp"): 80,
                ("www", "tcp"): 80,
                ("www", "udp"): 80,
                ("www-http", "tcp"): 80,
                ("www-http", "udp"): 80,
            },
        )

    def test_parseFile(self):
        """
        Services are parsed from given C{file}.
        """
        conf = inetdconf.ServicesConf()
        with open(self.servicesFilename2) as f:
            conf.parseFile(f)
        self.assertEqual(
            conf.services,
            {
                ("https", "tcp"): 443,
            },
        )

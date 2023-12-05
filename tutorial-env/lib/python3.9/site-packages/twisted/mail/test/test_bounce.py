# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

import email.message
import email.parser
from io import BytesIO, StringIO

from twisted.mail import bounce
from twisted.trial import unittest


class BounceTests(unittest.TestCase):
    """
    Bounce message generation
    """

    def test_bounceMessageUnicode(self):
        """
        L{twisted.mail.bounce.generateBounce} can accept L{unicode}.
        """
        fromAddress, to, s = bounce.generateBounce(
            StringIO(
                """\
From: Moshe Zadka <moshez@example.com>
To: nonexistent@example.org
Subject: test

"""
            ),
            "moshez@example.com",
            "nonexistent@example.org",
        )
        self.assertEqual(fromAddress, b"")
        self.assertEqual(to, b"moshez@example.com")
        emailParser = email.parser.Parser()
        mess = emailParser.parse(StringIO(s.decode("utf-8")))
        self.assertEqual(mess["To"], "moshez@example.com")
        self.assertEqual(mess["From"], "postmaster@example.org")
        self.assertEqual(mess["subject"], "Returned Mail: see transcript for details")

    def test_bounceMessageBytes(self):
        """
        L{twisted.mail.bounce.generateBounce} can accept L{bytes}.
        """
        fromAddress, to, s = bounce.generateBounce(
            BytesIO(
                b"""\
From: Moshe Zadka <moshez@example.com>
To: nonexistent@example.org
Subject: test

"""
            ),
            b"moshez@example.com",
            b"nonexistent@example.org",
        )
        self.assertEqual(fromAddress, b"")
        self.assertEqual(to, b"moshez@example.com")
        emailParser = email.parser.Parser()
        mess = emailParser.parse(StringIO(s.decode("utf-8")))
        self.assertEqual(mess["To"], "moshez@example.com")
        self.assertEqual(mess["From"], "postmaster@example.org")
        self.assertEqual(mess["subject"], "Returned Mail: see transcript for details")

    def test_bounceMessageCustomTranscript(self):
        """
        Pass a custom transcript message to L{twisted.mail.bounce.generateBounce}.
        """
        fromAddress, to, s = bounce.generateBounce(
            BytesIO(
                b"""\
From: Moshe Zadka <moshez@example.com>
To: nonexistent@example.org
Subject: test

"""
            ),
            b"moshez@example.com",
            b"nonexistent@example.org",
            "Custom transcript",
        )
        self.assertEqual(fromAddress, b"")
        self.assertEqual(to, b"moshez@example.com")
        emailParser = email.parser.Parser()
        mess = emailParser.parse(StringIO(s.decode("utf-8")))
        self.assertEqual(mess["To"], "moshez@example.com")
        self.assertEqual(mess["From"], "postmaster@example.org")
        self.assertEqual(mess["subject"], "Returned Mail: see transcript for details")
        self.assertTrue(mess.is_multipart())
        parts = mess.get_payload()
        self.assertEqual(parts[0].get_payload(), "Custom transcript\n")

    def _bounceBigMessage(self, header, message, ioType):
        """
        Pass a really big message to L{twisted.mail.bounce.generateBounce}.
        """
        fromAddress, to, s = bounce.generateBounce(
            ioType(header + message), "moshez@example.com", "nonexistent@example.org"
        )
        emailParser = email.parser.Parser()
        mess = emailParser.parse(StringIO(s.decode("utf-8")))
        self.assertEqual(mess["To"], "moshez@example.com")
        self.assertEqual(mess["From"], "postmaster@example.org")
        self.assertEqual(mess["subject"], "Returned Mail: see transcript for details")
        self.assertTrue(mess.is_multipart())
        parts = mess.get_payload()
        innerMessage = parts[1].get_payload()
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        self.assertEqual(innerMessage[0].get_payload() + "\n", message)

    def test_bounceBigMessage(self):
        """
        L{twisted.mail.bounce.generateBounce} with big L{unicode} and
        L{bytes} messages.
        """
        header = b"""\
From: Moshe Zadka <moshez@example.com>
To: nonexistent@example.org
Subject: test

"""
        self._bounceBigMessage(header, b"Test test\n" * 10000, BytesIO)
        self._bounceBigMessage(header.decode("utf-8"), "More test\n" * 10000, StringIO)

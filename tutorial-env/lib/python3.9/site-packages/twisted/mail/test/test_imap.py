# -*- test-case-name: twisted.mail.test.test_imap -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Test case for twisted.mail.imap4
"""

import base64
import codecs
import functools
import locale
import os
import uuid
from collections import OrderedDict
from io import BytesIO
from itertools import chain
from typing import List, Optional, Tuple, Type
from unittest import skipIf

from zope.interface import implementer
from zope.interface.verify import verifyClass, verifyObject

from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from twisted.cred.credentials import (
    CramMD5Credentials,
    IUsernameHashedPassword,
    IUsernamePassword,
)
from twisted.cred.error import UnauthorizedLogin
from twisted.cred.portal import IRealm, Portal
from twisted.internet import defer, error, interfaces, reactor
from twisted.internet.defer import Deferred
from twisted.internet.task import Clock
from twisted.mail import imap4
from twisted.mail.imap4 import MessageSet
from twisted.mail.interfaces import (
    IChallengeResponse,
    IClientAuthentication,
    ICloseableMailboxIMAP,
)
from twisted.protocols import loopback
from twisted.python import failure, log, util
from twisted.python.compat import iterbytes, nativeString, networkString
from twisted.test.proto_helpers import StringTransport, StringTransportWithDisconnection
from twisted.trial.unittest import SynchronousTestCase, TestCase

try:
    from twisted.test.ssl_helpers import ClientTLSContext, ServerTLSContext
except ImportError:
    ClientTLSContext = None  # type: ignore[assignment,misc]
    ServerTLSContext = None  # type: ignore[assignment,misc]


def strip(f):
    return lambda result, f=f: f()


class IMAP4UTF7Tests(TestCase):
    tests = [
        ["Hello world", b"Hello world"],
        ["Hello & world", b"Hello &- world"],
        ["Hello\xffworld", b"Hello&AP8-world"],
        ["\xff\xfe\xfd\xfc", b"&AP8A,gD9APw-"],
        [
            "~peter/mail/\u65e5\u672c\u8a9e/\u53f0\u5317",
            b"~peter/mail/&ZeVnLIqe-/&U,BTFw-",
        ],  # example from RFC 2060
    ]

    def test_encodeWithErrors(self):
        """
        Specifying an error policy to C{unicode.encode} with the
        I{imap4-utf-7} codec should produce the same result as not
        specifying the error policy.
        """
        text = "Hello world"
        self.assertEqual(
            text.encode("imap4-utf-7", "strict"), text.encode("imap4-utf-7")
        )

    def test_decodeWithErrors(self):
        """
        Similar to L{test_encodeWithErrors}, but for C{bytes.decode}.
        """
        bytes = b"Hello world"
        self.assertEqual(
            bytes.decode("imap4-utf-7", "strict"), bytes.decode("imap4-utf-7")
        )

    def test_encodeAmpersand(self):
        """
        Unicode strings that contain an ampersand (C{&}) can be
        encoded to bytes with the I{imap4-utf-7} codec.
        """
        text = "&Hello&\N{VULGAR FRACTION ONE HALF}&"
        self.assertEqual(
            text.encode("imap4-utf-7"),
            b"&-Hello&-&AL0-&-",
        )

    def test_decodeWithoutFinalASCIIShift(self):
        """
        An I{imap4-utf-7} encoded string that does not shift back to
        ASCII (i.e., it lacks a final C{-}) can be decoded.
        """
        self.assertEqual(
            b"&AL0".decode("imap4-utf-7"),
            "\N{VULGAR FRACTION ONE HALF}",
        )

    def test_getreader(self):
        """
        C{codecs.getreader('imap4-utf-7')} returns the I{imap4-utf-7} stream
        reader class.
        """
        reader = codecs.getreader("imap4-utf-7")(BytesIO(b"Hello&AP8-world"))
        self.assertEqual(reader.read(), "Hello\xffworld")

    def test_getwriter(self):
        """
        C{codecs.getwriter('imap4-utf-7')} returns the I{imap4-utf-7} stream
        writer class.
        """
        output = BytesIO()
        writer = codecs.getwriter("imap4-utf-7")(output)
        writer.write("Hello\xffworld")
        self.assertEqual(output.getvalue(), b"Hello&AP8-world")

    def test_encode(self):
        """
        The I{imap4-utf-7} can be used to encode a unicode string into a byte
        string according to the IMAP4 modified UTF-7 encoding rules.
        """
        for (input, output) in self.tests:
            self.assertEqual(input.encode("imap4-utf-7"), output)

    def test_decode(self):
        """
        The I{imap4-utf-7} can be used to decode a byte string into a unicode
        string according to the IMAP4 modified UTF-7 encoding rules.
        """
        for (input, output) in self.tests:
            self.assertEqual(input, output.decode("imap4-utf-7"))

    def test_printableSingletons(self):
        """
        The IMAP4 modified UTF-7 implementation encodes all printable
        characters which are in ASCII using the corresponding ASCII byte.
        """
        # All printables represent themselves
        for o in chain(range(0x20, 0x26), range(0x27, 0x7F)):
            charbyte = chr(o).encode()
            self.assertEqual(charbyte, chr(o).encode("imap4-utf-7"))
            self.assertEqual(chr(o), charbyte.decode("imap4-utf-7"))
        self.assertEqual("&".encode("imap4-utf-7"), b"&-")
        self.assertEqual(b"&-".decode("imap4-utf-7"), "&")


class BufferingConsumer:
    def __init__(self):
        self.buffer = []

    def write(self, bytes):
        self.buffer.append(bytes)
        if self.consumer:
            self.consumer.resumeProducing()

    def registerProducer(self, consumer, streaming):
        self.consumer = consumer
        self.consumer.resumeProducing()

    def unregisterProducer(self):
        self.consumer = None


class MessageProducerTests(SynchronousTestCase):
    def testSinglePart(self):
        body = b"This is body text.  Rar."
        headers = OrderedDict()
        headers["from"] = "sender@host"
        headers["to"] = "recipient@domain"
        headers["subject"] = "booga booga boo"
        headers["content-type"] = "text/plain"

        msg = FakeyMessage(headers, (), None, body, 123, None)

        c = BufferingConsumer()
        p = imap4.MessageProducer(msg)
        d = p.beginProducing(c)

        def cbProduced(result):
            self.assertIdentical(result, p)
            self.assertEqual(
                b"".join(c.buffer),
                b"{119}\r\n"
                b"From: sender@host\r\n"
                b"To: recipient@domain\r\n"
                b"Subject: booga booga boo\r\n"
                b"Content-Type: text/plain\r\n"
                b"\r\n" + body,
            )

        return d.addCallback(cbProduced)

    def testSingleMultiPart(self):
        outerBody = b""
        innerBody = b"Contained body message text.  Squarge."
        headers = OrderedDict()
        headers["from"] = "sender@host"
        headers["to"] = "recipient@domain"
        headers["subject"] = "booga booga boo"
        headers["content-type"] = 'multipart/alternative; boundary="xyz"'

        innerHeaders = OrderedDict()
        innerHeaders["subject"] = "this is subject text"
        innerHeaders["content-type"] = "text/plain"
        msg = FakeyMessage(
            headers,
            (),
            None,
            outerBody,
            123,
            [FakeyMessage(innerHeaders, (), None, innerBody, None, None)],
        )

        c = BufferingConsumer()
        p = imap4.MessageProducer(msg)
        d = p.beginProducing(c)

        def cbProduced(result):
            self.failUnlessIdentical(result, p)

            self.assertEqual(
                b"".join(c.buffer),
                b"{239}\r\n"
                b"From: sender@host\r\n"
                b"To: recipient@domain\r\n"
                b"Subject: booga booga boo\r\n"
                b'Content-Type: multipart/alternative; boundary="xyz"\r\n'
                b"\r\n"
                b"\r\n"
                b"--xyz\r\n"
                b"Subject: this is subject text\r\n"
                b"Content-Type: text/plain\r\n"
                b"\r\n" + innerBody + b"\r\n--xyz--\r\n",
            )

        return d.addCallback(cbProduced)

    def testMultipleMultiPart(self):
        outerBody = b""
        innerBody1 = b"Contained body message text.  Squarge."
        innerBody2 = b"Secondary <i>message</i> text of squarge body."
        headers = OrderedDict()
        headers["from"] = "sender@host"
        headers["to"] = "recipient@domain"
        headers["subject"] = "booga booga boo"
        headers["content-type"] = 'multipart/alternative; boundary="xyz"'
        innerHeaders = OrderedDict()
        innerHeaders["subject"] = "this is subject text"
        innerHeaders["content-type"] = "text/plain"
        innerHeaders2 = OrderedDict()
        innerHeaders2["subject"] = "<b>this is subject</b>"
        innerHeaders2["content-type"] = "text/html"
        msg = FakeyMessage(
            headers,
            (),
            None,
            outerBody,
            123,
            [
                FakeyMessage(innerHeaders, (), None, innerBody1, None, None),
                FakeyMessage(innerHeaders2, (), None, innerBody2, None, None),
            ],
        )

        c = BufferingConsumer()
        p = imap4.MessageProducer(msg)
        d = p.beginProducing(c)

        def cbProduced(result):
            self.failUnlessIdentical(result, p)

            self.assertEqual(
                b"".join(c.buffer),
                b"{354}\r\n"
                b"From: sender@host\r\n"
                b"To: recipient@domain\r\n"
                b"Subject: booga booga boo\r\n"
                b'Content-Type: multipart/alternative; boundary="xyz"\r\n'
                b"\r\n"
                b"\r\n"
                b"--xyz\r\n"
                b"Subject: this is subject text\r\n"
                b"Content-Type: text/plain\r\n"
                b"\r\n" + innerBody1 + b"\r\n--xyz\r\n"
                b"Subject: <b>this is subject</b>\r\n"
                b"Content-Type: text/html\r\n"
                b"\r\n" + innerBody2 + b"\r\n--xyz--\r\n",
            )

        return d.addCallback(cbProduced)

    def test_multiPartNoBoundary(self):
        """
        A boundary is generated if none is provided.
        """
        outerBody = b""
        innerBody = b"Contained body message text.  Squarge."
        headers = OrderedDict()
        headers["from"] = "sender@host"
        headers["to"] = "recipient@domain"
        headers["subject"] = "booga booga boo"
        headers["content-type"] = "multipart/alternative"

        innerHeaders = OrderedDict()
        innerHeaders["subject"] = "this is subject text"
        innerHeaders["content-type"] = "text/plain"
        msg = FakeyMessage(
            headers,
            (),
            None,
            outerBody,
            123,
            [FakeyMessage(innerHeaders, (), None, innerBody, None, None)],
        )

        c = BufferingConsumer()
        p = imap4.MessageProducer(msg)
        p._uuid4 = lambda: uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

        d = p.beginProducing(c)

        def cbProduced(result):
            self.failUnlessIdentical(result, p)
            self.assertEqual(
                b"".join(c.buffer),
                b"{341}\r\n"
                b"From: sender@host\r\n"
                b"To: recipient@domain\r\n"
                b"Subject: booga booga boo\r\n"
                b"Content-Type: multipart/alternative; boundary="
                b'"----=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"'
                b"\r\n"
                b"\r\n"
                b"\r\n"
                b"------=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\n"
                b"Subject: this is subject text\r\n"
                b"Content-Type: text/plain\r\n"
                b"\r\n"
                + innerBody
                + b"\r\n------=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa--\r\n",
            )

        return d.addCallback(cbProduced)

    def test_multiPartNoQuotes(self):
        """
        A boundary without does not have them added.
        """
        outerBody = b""
        innerBody = b"Contained body message text.  Squarge."
        headers = OrderedDict()
        headers["from"] = "sender@host"
        headers["to"] = "recipient@domain"
        headers["subject"] = "booga booga boo"
        headers["content-type"] = "multipart/alternative; boundary=xyz"

        innerHeaders = OrderedDict()
        innerHeaders["subject"] = "this is subject text"
        innerHeaders["content-type"] = "text/plain"
        msg = FakeyMessage(
            headers,
            (),
            None,
            outerBody,
            123,
            [FakeyMessage(innerHeaders, (), None, innerBody, None, None)],
        )

        c = BufferingConsumer()
        p = imap4.MessageProducer(msg)
        d = p.beginProducing(c)

        def cbProduced(result):
            self.failUnlessIdentical(result, p)
            self.assertEqual(
                b"".join(c.buffer),
                b"{237}\r\n"
                b"From: sender@host\r\n"
                b"To: recipient@domain\r\n"
                b"Subject: booga booga boo\r\n"
                b"Content-Type: multipart/alternative; boundary="
                b"xyz"
                b"\r\n"
                b"\r\n"
                b"\r\n"
                b"--xyz\r\n"
                b"Subject: this is subject text\r\n"
                b"Content-Type: text/plain\r\n"
                b"\r\n" + innerBody + b"\r\n--xyz--\r\n",
            )

        return d.addCallback(cbProduced)


class MessageSetTests(SynchronousTestCase):
    """
    Tests for L{MessageSet}.
    """

    def test_equalityIterationAndAddition(self):
        """
        Test the following properties of L{MessageSet} addition and
        equality:

            1. Two empty L{MessageSet}s are equal to each other;

            2. A L{MessageSet} is not equal to any other object;

            2. Adding a L{MessageSet} and another L{MessageSet} or an
               L{int} representing a single message or a sequence of
               L{int}s representing a sequence of message numbers
               produces a new L{MessageSet} that:

            3. Has a length equal to the number of messages within
               each sequence of message numbers;

            4. Yields each message number in ascending order when
               iterated over;

            6. L{MessageSet.add} with a single message or a start and
               end message satisfies 3 and 4 above.
        """
        m1 = MessageSet()
        m2 = MessageSet()

        self.assertEqual(m1, m2)
        self.assertNotEqual(m1, ())

        m1 = m1 + 1
        self.assertEqual(len(m1), 1)
        self.assertEqual(list(m1), [1])

        m1 = m1 + (1, 3)
        self.assertEqual(len(m1), 3)
        self.assertEqual(list(m1), [1, 2, 3])

        m2 = m2 + (1, 3)
        self.assertEqual(m1, m2)
        self.assertEqual(list(m1 + m2), [1, 2, 3])

        m1.add(5)
        self.assertEqual(len(m1), 4)
        self.assertEqual(list(m1), [1, 2, 3, 5])

        self.assertNotEqual(m1, m2)

        m1.add(6, 8)
        self.assertEqual(len(m1), 7)
        self.assertEqual(list(m1), [1, 2, 3, 5, 6, 7, 8])

    def test_lengthWithWildcardRange(self):
        """
        A L{MessageSet} that has a range that ends with L{None} raises
        a L{TypeError} when its length is requested.
        """
        self.assertRaises(TypeError, len, MessageSet(1, None))

    def test_reprSanity(self):
        """
        L{MessageSet.__repr__} does not raise an exception
        """
        repr(MessageSet(1, 2))

    def test_stringRepresentationWithWildcards(self):
        """
        In a L{MessageSet}, in the presence of wildcards, if the
        highest message id is known, the wildcard should get replaced
        by that high value.
        """
        inputs = [
            imap4.parseIdList(b"*"),
            imap4.parseIdList(b"1:*"),
            imap4.parseIdList(b"3:*", 6),
            imap4.parseIdList(b"*:2", 6),
        ]

        outputs = [
            "*",
            "1:*",
            "3:6",
            "2:6",
        ]

        for i, o in zip(inputs, outputs):
            self.assertEqual(str(i), o)

    def test_stringRepresentationWithInversion(self):
        """
        In a L{MessageSet}, inverting the high and low numbers in a
        range doesn't affect the meaning of the range.  For example,
        3:2 displays just like 2:3, because according to the RFC they
        have the same meaning.
        """
        inputs = [
            imap4.parseIdList(b"2:3"),
            imap4.parseIdList(b"3:2"),
        ]

        outputs = [
            "2:3",
            "2:3",
        ]

        for i, o in zip(inputs, outputs):
            self.assertEqual(str(i), o)

    def test_createWithSingleMessageNumber(self):
        """
        Creating a L{MessageSet} with a single message number adds
        only that message to the L{MessageSet}; its serialized form
        includes only that message number, its length is one, and it
        yields only that message number.
        """
        m = MessageSet(1)
        self.assertEqual(str(m), "1")
        self.assertEqual(len(m), 1)
        self.assertEqual(list(m), [1])

    def test_createWithSequence(self):
        """
        Creating a L{MessageSet} with both a start and end message
        number adds the sequence between to the L{MessageSet}; its
        serialized form consists that range, its length is the length
        of the sequence, and it yields the message numbers inclusively
        between the start and end.
        """
        m = MessageSet(1, 10)
        self.assertEqual(str(m), "1:10")
        self.assertEqual(len(m), 10)
        self.assertEqual(list(m), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

    def test_createWithSingleWildcard(self):
        """
        Creating a L{MessageSet} with a single L{None}, representing
        C{*}, adds C{*} to the range; its serialized form includes
        only C{*}, its length is one, but it cannot be iterated over
        because its endpoint is unknown.
        """
        m = MessageSet(None)
        self.assertEqual(str(m), "*")
        self.assertEqual(len(m), 1)
        self.assertRaises(TypeError, list, m)

    def test_setLastSingleWildcard(self):
        """
        Setting L{MessageSet.last} replaces L{None}, representing
        C{*}, with that number, making that L{MessageSet} iterable.
        """
        singleMessageReplaced = MessageSet(None)
        singleMessageReplaced.last = 10
        self.assertEqual(list(singleMessageReplaced), [10])

        rangeReplaced = MessageSet(3, None)
        rangeReplaced.last = 1
        self.assertEqual(list(rangeReplaced), [1, 2, 3])

    def test_setLastWithWildcardRange(self):
        """
        Setting L{MessageSet.last} replaces L{None} in all ranges.
        """
        m = MessageSet(1, None)
        m.add(2, None)
        m.last = 5
        self.assertEqual(list(m), [1, 2, 3, 4, 5])

    def test_setLastTwiceFails(self):
        """
        L{MessageSet.last} cannot be set twice.
        """
        m = MessageSet(1, None)
        m.last = 2
        with self.assertRaises(ValueError):
            m.last = 3

    def test_lastOverridesNoneInAdd(self):
        """
        Adding a L{None}, representing C{*}, or a sequence that
        includes L{None} to a L{MessageSet} whose
        L{last<MessageSet.last>} property has been set replaces all
        occurrences of L{None} with the value of
        L{last<MessageSet.last>}.
        """
        hasLast = MessageSet(1)
        hasLast.last = 4

        hasLast.add(None)
        self.assertEqual(list(hasLast), [1, 4])

        self.assertEqual(list(hasLast + (None, 5)), [1, 4, 5])

        hasLast.add(3, None)
        self.assertEqual(list(hasLast), [1, 3, 4])

    def test_getLast(self):
        """
        Accessing L{MessageSet.last} returns the last value.
        """
        m = MessageSet(1, None)
        m.last = 2
        self.assertEqual(m.last, 2)

    def test_extend(self):
        """
        L{MessageSet.extend} accepts as its arugment an L{int} or
        L{None}, or a sequence L{int}s or L{None}s of length two, or
        another L{MessageSet}, combining its argument with its
        instance's existing ranges.
        """
        extendWithInt = MessageSet()
        extendWithInt.extend(1)
        self.assertEqual(list(extendWithInt), [1])

        extendWithNone = MessageSet()
        extendWithNone.extend(None)
        self.assertEqual(str(extendWithNone), "*")

        extendWithSequenceOfInts = MessageSet()
        extendWithSequenceOfInts.extend((1, 3))
        self.assertEqual(list(extendWithSequenceOfInts), [1, 2, 3])

        extendWithSequenceOfNones = MessageSet()
        extendWithSequenceOfNones.extend((None, None))
        self.assertEqual(str(extendWithSequenceOfNones), "*")

        extendWithMessageSet = MessageSet()
        extendWithMessageSet.extend(MessageSet(1, 3))
        self.assertEqual(list(extendWithMessageSet), [1, 2, 3])

    def test_contains(self):
        """
        A L{MessageSet} contains a number if the number falls within
        one of its ranges, and raises L{TypeError} if any range
        contains L{None}.
        """
        hasFive = MessageSet(1, 7)
        doesNotHaveFive = MessageSet(1, 4) + MessageSet(6, 7)

        self.assertIn(5, hasFive)
        self.assertNotIn(5, doesNotHaveFive)

        hasFiveButHasNone = hasFive + None
        with self.assertRaises(TypeError):
            5 in hasFiveButHasNone

        hasFiveButHasNoneInSequence = hasFive + (10, 12)
        hasFiveButHasNoneInSequence.add(8, None)
        with self.assertRaises(TypeError):
            5 in hasFiveButHasNoneInSequence

    def test_rangesMerged(self):
        """
        Adding a sequence of message numbers to a L{MessageSet} that
        begins or ends immediately before or after an existing
        sequence in that L{MessageSet}, or overlaps one, merges the two.
        """

        mergeAfter = MessageSet(1, 3)
        mergeBefore = MessageSet(6, 8)

        mergeBetweenSequence = mergeAfter + mergeBefore
        mergeBetweenNumber = mergeAfter + MessageSet(5, 7)

        self.assertEqual(list(mergeAfter + (2, 4)), [1, 2, 3, 4])
        self.assertEqual(list(mergeAfter + (3, 5)), [1, 2, 3, 4, 5])

        self.assertEqual(list(mergeBefore + (5, 7)), [5, 6, 7, 8])
        self.assertEqual(list(mergeBefore + (4, 6)), [4, 5, 6, 7, 8])

        self.assertEqual(list(mergeBetweenSequence + (3, 5)), [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(
            list(mergeBetweenNumber + MessageSet(4)), [1, 2, 3, 4, 5, 6, 7]
        )

    def test_seq_rangeExamples(self):
        """
        Test the C{seq-range} examples from Section 9, "Formal Syntax"
        of RFC 3501::

            Example: 2:4 and 4:2 are equivalent and indicate values
                     2, 3, and 4.

            Example: a unique identifier sequence range of
                     3291:* includes the UID of the last message in
                     the mailbox, even if that value is less than 3291.

        @see: U{http://tools.ietf.org/html/rfc3501#section-9}
        """

        self.assertEqual(MessageSet(2, 4), MessageSet(4, 2))
        self.assertEqual(list(MessageSet(2, 4)), [2, 3, 4])

        m = MessageSet(3291, None)
        m.last = 3290
        self.assertEqual(list(m), [3290, 3291])

    def test_sequence_setExamples(self):
        """
        Test the C{sequence-set} examples from Section 9, "Formal
        Syntax" of RFC 3501.  In particular, L{MessageSet} reorders
        and coalesces overlaps::

            Example: a message sequence number set of
                     2,4:7,9,12:* for a mailbox with 15 messages is
                     equivalent to 2,4,5,6,7,9,12,13,14,15

            Example: a message sequence number set of *:4,5:7
                     for a mailbox with 10 messages is equivalent to
                     10,9,8,7,6,5,4,5,6,7 and MAY be reordered and
                     overlap coalesced to be 4,5,6,7,8,9,10.

        @see: U{http://tools.ietf.org/html/rfc3501#section-9}
        """
        fromFifteenMessages = (
            MessageSet(2) + MessageSet(4, 7) + MessageSet(9) + MessageSet(12, None)
        )
        fromFifteenMessages.last = 15
        self.assertEqual(
            ",".join(str(i) for i in fromFifteenMessages), "2,4,5,6,7,9,12,13,14,15"
        )

        fromTenMessages = MessageSet(None, 4) + MessageSet(5, 7)
        fromTenMessages.last = 10
        self.assertEqual(",".join(str(i) for i in fromTenMessages), "4,5,6,7,8,9,10")


class IMAP4HelperTests(TestCase):
    """
    Tests for various helper utilities in the IMAP4 module.
    """

    def test_commandRepr(self):
        """
        L{imap4.Command}'s C{repr} does not raise an exception.
        """
        repr(imap4.Command(b"COMMAND", [b"arg"], (b"extra")))

    def test_fileProducer(self):
        b = ((b"x" * 1) + (b"y" * 1) + (b"z" * 1)) * 10
        c = BufferingConsumer()
        f = BytesIO(b)
        p = imap4.FileProducer(f)
        d = p.beginProducing(c)

        def cbProduced(result):
            self.failUnlessIdentical(result, p)
            self.assertEqual(b"{%d}\r\n%b" % (len(b), b), b"".join(c.buffer))
            return result

        def cbResume(result):
            # Calling resumeProducing after completion does not raise
            # an exception
            p.resumeProducing()
            return result

        d.addCallback(cbProduced)
        d.addCallback(cbResume)
        # The second cbProduced ensures calling resumeProducing after
        # completion does not change the result.
        return d.addCallback(cbProduced)

    def test_wildcard(self):
        cases = [
            [
                "foo/%gum/bar",
                ["foo/bar", "oo/lalagum/bar", "foo/gumx/bar", "foo/gum/baz"],
                ["foo/xgum/bar", "foo/gum/bar"],
            ],
            [
                "foo/x%x/bar",
                ["foo", "bar", "fuz fuz fuz", "foo/*/bar", "foo/xyz/bar", "foo/xx/baz"],
                ["foo/xyx/bar", "foo/xx/bar", "foo/xxxxxxxxxxxxxx/bar"],
            ],
            [
                "foo/xyz*abc/bar",
                ["foo/xyz/bar", "foo/abc/bar", "foo/xyzab/cbar", "foo/xyza/bcbar"],
                ["foo/xyzabc/bar", "foo/xyz/abc/bar", "foo/xyz/123/abc/bar"],
            ],
        ]

        for (wildcard, fail, succeed) in cases:
            wildcard = imap4.wildcardToRegexp(wildcard, "/")
            for x in fail:
                self.assertFalse(wildcard.match(x))
            for x in succeed:
                self.assertTrue(wildcard.match(x))

    def test_wildcardNoDelim(self):
        cases = [
            [
                "foo/%gum/bar",
                ["foo/bar", "oo/lalagum/bar", "foo/gumx/bar", "foo/gum/baz"],
                ["foo/xgum/bar", "foo/gum/bar", "foo/x/gum/bar"],
            ],
            [
                "foo/x%x/bar",
                ["foo", "bar", "fuz fuz fuz", "foo/*/bar", "foo/xyz/bar", "foo/xx/baz"],
                ["foo/xyx/bar", "foo/xx/bar", "foo/xxxxxxxxxxxxxx/bar", "foo/x/x/bar"],
            ],
            [
                "foo/xyz*abc/bar",
                ["foo/xyz/bar", "foo/abc/bar", "foo/xyzab/cbar", "foo/xyza/bcbar"],
                ["foo/xyzabc/bar", "foo/xyz/abc/bar", "foo/xyz/123/abc/bar"],
            ],
        ]

        for (wildcard, fail, succeed) in cases:
            wildcard = imap4.wildcardToRegexp(wildcard, None)
            for x in fail:
                self.assertFalse(wildcard.match(x), x)
            for x in succeed:
                self.assertTrue(wildcard.match(x), x)

    def test_headerFormatter(self):
        """
        L{imap4._formatHeaders} accepts a C{dict} of header name/value pairs and
        returns a string representing those headers in the standard multiline,
        C{":"}-separated format.
        """
        cases = [
            (
                {"Header1": "Value1", "Header2": "Value2"},
                b"Header2: Value2\r\nHeader1: Value1\r\n",
            ),
        ]

        for (input, expected) in cases:
            output = imap4._formatHeaders(input)
            self.assertEqual(
                sorted(output.splitlines(True)), sorted(expected.splitlines(True))
            )

    def test_quotedSplitter(self):
        cases = [
            b"""Hello World""",
            b'''Hello "World!"''',
            b'''World "Hello" "How are you?"''',
            b'''"Hello world" How "are you?"''',
            b"""foo bar "baz buz" NIL""",
            b'''foo bar "baz buz" "NIL"''',
            b"""foo NIL "baz buz" bar""",
            b"""foo "NIL" "baz buz" bar""",
            b""""NIL" bar "baz buz" foo""",
            b'oo \\"oo\\" oo',
            b'"oo \\"oo\\" oo"',
            b"oo \t oo",
            b'"oo \t oo"',
            b"oo \\t oo",
            b'"oo \\t oo"',
            br"oo \o oo",
            br'"oo \o oo"',
            b"oo \\o oo",
            b'"oo \\o oo"',
        ]

        answers = [
            [b"Hello", b"World"],
            [b"Hello", b"World!"],
            [b"World", b"Hello", b"How are you?"],
            [b"Hello world", b"How", b"are you?"],
            [b"foo", b"bar", b"baz buz", None],
            [b"foo", b"bar", b"baz buz", b"NIL"],
            [b"foo", None, b"baz buz", b"bar"],
            [b"foo", b"NIL", b"baz buz", b"bar"],
            [b"NIL", b"bar", b"baz buz", b"foo"],
            [b"oo", b'"oo"', b"oo"],
            [b'oo "oo" oo'],
            [b"oo", b"oo"],
            [b"oo \t oo"],
            [b"oo", b"\\t", b"oo"],
            [b"oo \\t oo"],
            [b"oo", br"\o", b"oo"],
            [br"oo \o oo"],
            [b"oo", b"\\o", b"oo"],
            [b"oo \\o oo"],
        ]

        errors = [
            b'"mismatched quote',
            b'mismatched quote"',
            b'mismatched"quote',
            b'"oops here is" another"',
        ]

        for s in errors:
            self.assertRaises(imap4.MismatchedQuoting, imap4.splitQuoted, s)

        for (case, expected) in zip(cases, answers):
            self.assertEqual(imap4.splitQuoted(case), expected)

    def test_stringCollapser(self):
        cases = [
            [b"a", b"b", b"c", b"d", b"e"],
            [b"a", b" ", b'"', b"b", b"c", b" ", b'"', b" ", b"d", b"e"],
            [[b"a", b"b", b"c"], b"d", b"e"],
            [b"a", [b"b", b"c", b"d"], b"e"],
            [b"a", b"b", [b"c", b"d", b"e"]],
            [b'"', b"a", b" ", b'"', [b"b", b"c", b"d"], b'"', b" ", b"e", b'"'],
            [b"a", [b'"', b" ", b"b", b"c", b" ", b" ", b'"'], b"d", b"e"],
        ]

        answers = [
            [b"abcde"],
            [b"a", b"bc ", b"de"],
            [[b"abc"], b"de"],
            [b"a", [b"bcd"], b"e"],
            [b"ab", [b"cde"]],
            [b"a ", [b"bcd"], b" e"],
            [b"a", [b" bc  "], b"de"],
        ]

        for (case, expected) in zip(cases, answers):
            self.assertEqual(imap4.collapseStrings(case), expected)

    def test_parenParser(self):
        s = b"\r\n".join([b"xx"] * 4)

        def check(case, expected):
            parsed = imap4.parseNestedParens(case)
            self.assertEqual(parsed, [expected])
            # XXX This code used to work, but changes occurred within the
            # imap4.py module which made it no longer necessary for *all* of it
            # to work.  In particular, only the part that makes
            # 'BODY.PEEK[HEADER.FIELDS.NOT (Subject Bcc Cc)]' come out
            # correctly no longer needs to work.  So, I am loathe to delete the
            # entire section of the test. --exarkun

            # self.assertEqual(b'(' + imap4.collapseNestedLists(parsed) + b')',
            #                  expected)

        check(
            b"(BODY.PEEK[HEADER.FIELDS.NOT (subject bcc cc)] {%d}\r\n%b)" % (len(s), s),
            [b"BODY.PEEK", [b"HEADER.FIELDS.NOT", [b"subject", b"bcc", b"cc"]], s],
        )
        check(
            b'(FLAGS (\\Seen) INTERNALDATE "17-Jul-1996 02:44:25 -0700" '
            b"RFC822.SIZE 4286 ENVELOPE "
            b'("Wed, 17 Jul 1996 02:23:25 -0700 (PDT)" '
            b'"IMAP4rev1 WG mtg summary and minutes" '
            b'(("Terry Gray" NIL gray cac.washington.edu)) '
            b'(("Terry Gray" NIL gray cac.washington.edu)) '
            b'(("Terry Gray" NIL gray cac.washington.edu)) '
            b"((NIL NIL imap cac.washington.edu)) "
            b"((NIL NIL minutes CNRI.Reston.VA.US) "
            b'("John Klensin" NIL KLENSIN INFOODS.MIT.EDU)) NIL NIL '
            b"<B27397-0100000@cac.washington.edu>) "
            b"BODY (TEXT PLAIN (CHARSET US-ASCII) NIL NIL 7BIT 3028 92))",
            [
                b"FLAGS",
                [br"\Seen"],
                b"INTERNALDATE",
                b"17-Jul-1996 02:44:25 -0700",
                b"RFC822.SIZE",
                b"4286",
                b"ENVELOPE",
                [
                    b"Wed, 17 Jul 1996 02:23:25 -0700 (PDT)",
                    b"IMAP4rev1 WG mtg summary and minutes",
                    [[b"Terry Gray", None, b"gray", b"cac.washington.edu"]],
                    [[b"Terry Gray", None, b"gray", b"cac.washington.edu"]],
                    [[b"Terry Gray", None, b"gray", b"cac.washington.edu"]],
                    [[None, None, b"imap", b"cac.washington.edu"]],
                    [
                        [None, None, b"minutes", b"CNRI.Reston.VA.US"],
                        [b"John Klensin", None, b"KLENSIN", b"INFOODS.MIT.EDU"],
                    ],
                    None,
                    None,
                    b"<B27397-0100000@cac.washington.edu>",
                ],
                b"BODY",
                [
                    b"TEXT",
                    b"PLAIN",
                    [b"CHARSET", b"US-ASCII"],
                    None,
                    None,
                    b"7BIT",
                    b"3028",
                    b"92",
                ],
            ],
        )

        check(b'("oo \\"oo\\" oo")', [b'oo "oo" oo'])
        check(b'("oo \\\\ oo")', [b"oo \\\\ oo"])
        check(b'("oo \\ oo")', [b"oo \\ oo"])

        check(b'("oo \\o")', [b"oo \\o"])
        check(br'("oo \o")', [br"oo \o"])
        check(br"(oo \o)", [b"oo", br"\o"])
        check(b"(oo \\o)", [b"oo", b"\\o"])

    def test_fetchParserSimple(self):
        cases = [
            ["ENVELOPE", "Envelope", "envelope"],
            ["FLAGS", "Flags", "flags"],
            ["INTERNALDATE", "InternalDate", "internaldate"],
            ["RFC822.HEADER", "RFC822Header", "rfc822.header"],
            ["RFC822.SIZE", "RFC822Size", "rfc822.size"],
            ["RFC822.TEXT", "RFC822Text", "rfc822.text"],
            ["RFC822", "RFC822", "rfc822"],
            ["UID", "UID", "uid"],
            ["BODYSTRUCTURE", "BodyStructure", "bodystructure"],
        ]

        for (inp, outp, asString) in cases:
            inp = inp.encode("ascii")
            p = imap4._FetchParser()
            p.parseString(inp)
            self.assertEqual(len(p.result), 1)
            self.assertTrue(isinstance(p.result[0], getattr(p, outp)))
            self.assertEqual(str(p.result[0]), asString)

    def test_fetchParserMacros(self):
        cases = [
            [b"ALL", (4, [b"flags", b"internaldate", b"rfc822.size", b"envelope"])],
            [
                b"FULL",
                (5, [b"flags", b"internaldate", b"rfc822.size", b"envelope", b"body"]),
            ],
            [b"FAST", (3, [b"flags", b"internaldate", b"rfc822.size"])],
        ]

        for (inp, outp) in cases:
            p = imap4._FetchParser()
            p.parseString(inp)
            self.assertEqual(len(p.result), outp[0])
            expectedResult = [str(token).lower().encode("ascii") for token in p.result]
            expectedResult.sort()
            outp[1].sort()
            self.assertEqual(expectedResult, outp[1])

    def test_fetchParserBody(self):
        P = imap4._FetchParser

        p = P()
        p.parseString(b"BODY")
        self.assertEqual(len(p.result), 1)
        self.assertTrue(isinstance(p.result[0], p.Body))
        self.assertEqual(p.result[0].peek, False)
        self.assertEqual(p.result[0].header, None)
        self.assertEqual(str(p.result[0]), "BODY")

        p = P()
        p.parseString(b"BODY.PEEK")
        self.assertEqual(len(p.result), 1)
        self.assertTrue(isinstance(p.result[0], p.Body))
        self.assertEqual(p.result[0].peek, True)
        self.assertEqual(str(p.result[0]), "BODY")

        p = P()
        p.parseString(b"BODY[]")
        self.assertEqual(len(p.result), 1)
        self.assertTrue(isinstance(p.result[0], p.Body))
        self.assertEqual(p.result[0].empty, True)
        self.assertEqual(str(p.result[0]), "BODY[]")

        p = P()
        p.parseString(b"BODY[HEADER]")
        self.assertEqual(len(p.result), 1)
        self.assertTrue(isinstance(p.result[0], p.Body))
        self.assertEqual(p.result[0].peek, False)
        self.assertTrue(isinstance(p.result[0].header, p.Header))
        self.assertEqual(p.result[0].header.negate, True)
        self.assertEqual(p.result[0].header.fields, ())
        self.assertEqual(p.result[0].empty, False)
        self.assertEqual(str(p.result[0]), "BODY[HEADER]")

        p = P()
        p.parseString(b"BODY.PEEK[HEADER]")
        self.assertEqual(len(p.result), 1)
        self.assertTrue(isinstance(p.result[0], p.Body))
        self.assertEqual(p.result[0].peek, True)
        self.assertTrue(isinstance(p.result[0].header, p.Header))
        self.assertEqual(p.result[0].header.negate, True)
        self.assertEqual(p.result[0].header.fields, ())
        self.assertEqual(p.result[0].empty, False)
        self.assertEqual(str(p.result[0]), "BODY[HEADER]")

        p = P()
        p.parseString(b"BODY[HEADER.FIELDS (Subject Cc Message-Id)]")
        self.assertEqual(len(p.result), 1)
        self.assertTrue(isinstance(p.result[0], p.Body))
        self.assertEqual(p.result[0].peek, False)
        self.assertTrue(isinstance(p.result[0].header, p.Header))
        self.assertEqual(p.result[0].header.negate, False)
        self.assertEqual(p.result[0].header.fields, [b"SUBJECT", b"CC", b"MESSAGE-ID"])
        self.assertEqual(p.result[0].empty, False)
        self.assertEqual(
            bytes(p.result[0]), b"BODY[HEADER.FIELDS (Subject Cc Message-Id)]"
        )

        p = P()
        p.parseString(b"BODY.PEEK[HEADER.FIELDS (Subject Cc Message-Id)]")
        self.assertEqual(len(p.result), 1)
        self.assertTrue(isinstance(p.result[0], p.Body))
        self.assertEqual(p.result[0].peek, True)
        self.assertTrue(isinstance(p.result[0].header, p.Header))
        self.assertEqual(p.result[0].header.negate, False)
        self.assertEqual(p.result[0].header.fields, [b"SUBJECT", b"CC", b"MESSAGE-ID"])
        self.assertEqual(p.result[0].empty, False)
        self.assertEqual(
            bytes(p.result[0]), b"BODY[HEADER.FIELDS (Subject Cc Message-Id)]"
        )

        p = P()
        p.parseString(b"BODY.PEEK[HEADER.FIELDS.NOT (Subject Cc Message-Id)]")
        self.assertEqual(len(p.result), 1)
        self.assertTrue(isinstance(p.result[0], p.Body))
        self.assertEqual(p.result[0].peek, True)
        self.assertTrue(isinstance(p.result[0].header, p.Header))
        self.assertEqual(p.result[0].header.negate, True)
        self.assertEqual(p.result[0].header.fields, [b"SUBJECT", b"CC", b"MESSAGE-ID"])
        self.assertEqual(p.result[0].empty, False)
        self.assertEqual(
            bytes(p.result[0]), b"BODY[HEADER.FIELDS.NOT (Subject Cc Message-Id)]"
        )

        p = P()
        p.parseString(b"BODY[1.MIME]<10.50>")
        self.assertEqual(len(p.result), 1)
        self.assertTrue(isinstance(p.result[0], p.Body))
        self.assertEqual(p.result[0].peek, False)
        self.assertTrue(isinstance(p.result[0].mime, p.MIME))
        self.assertEqual(p.result[0].part, (0,))
        self.assertEqual(p.result[0].partialBegin, 10)
        self.assertEqual(p.result[0].partialLength, 50)
        self.assertEqual(p.result[0].empty, False)
        self.assertEqual(bytes(p.result[0]), b"BODY[1.MIME]<10.50>")

        p = P()
        p.parseString(
            b"BODY.PEEK[1.3.9.11.HEADER.FIELDS.NOT (Message-Id Date)]<103.69>"
        )
        self.assertEqual(len(p.result), 1)
        self.assertTrue(isinstance(p.result[0], p.Body))
        self.assertEqual(p.result[0].peek, True)
        self.assertTrue(isinstance(p.result[0].header, p.Header))
        self.assertEqual(p.result[0].part, (0, 2, 8, 10))
        self.assertEqual(p.result[0].header.fields, [b"MESSAGE-ID", b"DATE"])
        self.assertEqual(p.result[0].partialBegin, 103)
        self.assertEqual(p.result[0].partialLength, 69)
        self.assertEqual(p.result[0].empty, False)
        self.assertEqual(
            bytes(p.result[0]),
            b"BODY[1.3.9.11.HEADER.FIELDS.NOT (Message-Id Date)]<103.69>",
        )

    def test_fetchParserQuotedHeader(self):
        """
        Parsing a C{BODY} whose C{HEADER} values require quoting
        results in a object that perserves that quoting when
        serialized.
        """
        p = imap4._FetchParser()
        p.parseString(b"BODY[HEADER.FIELDS ((Quoted)]")
        self.assertEqual(len(p.result), 1)
        self.assertEqual(p.result[0].peek, False)
        self.assertIsInstance(p.result[0], p.Body)
        self.assertIsInstance(p.result[0].header, p.Header)
        self.assertEqual(bytes(p.result[0]), b'BODY[HEADER.FIELDS ("(Quoted")]')

    def test_fetchParserEmptyString(self):
        """
        Parsing an empty string results in no data.
        """
        p = imap4._FetchParser()
        p.parseString(b"")
        self.assertFalse(len(p.result))

    def test_fetchParserUnknownAttribute(self):
        """
        Parsing a string with an unknown attribute raises an
        L{Exception}.
        """
        p = imap4._FetchParser()
        self.assertRaises(Exception, p.parseString, b"UNKNOWN")

    def test_fetchParserIncompleteStringEndsInWhitespace(self):
        """
        Parsing a string that prematurely ends in whitespace raises an
        L{Exception}.
        """
        p = imap4._FetchParser()
        self.assertRaises(Exception, p.parseString, b"BODY[HEADER.FIELDS  ")

    def test_fetchParserExpectedWhitespace(self):
        """
        Parsing a string that contains an unexpected character rather
        than whitespace raises an L{Exception}.
        """
        p = imap4._FetchParser()
        self.assertRaises(Exception, p.parseString, b"BODY[HEADER.FIELDS!]")

    def test_fetchParserTextSection(self):
        """
        A C{BODY} can contain a C{TEXT} section.
        """
        p = imap4._FetchParser()
        p.parseString(b"BODY[TEXT]")
        self.assertEqual(len(p.result), 1)
        self.assertIsInstance(p.result[0], p.Body)
        self.assertEqual(p.result[0].peek, False)
        self.assertIsInstance(p.result[0].text, p.Text)
        self.assertEqual(bytes(p.result[0]), b"BODY[TEXT]")

    def test_fetchParserUnknownSection(self):
        """
        Parsing a C{BODY} with an unknown section raises an
        L{Exception}.
        """
        p = imap4._FetchParser()
        self.assertRaises(Exception, p.parseString, b"BODY[UNKNOWN]")

    def test_fetchParserMissingSectionClose(self):
        """
        Parsing a C{BODY} with an unterminated section list raises an
        L{Exception}.
        """
        p = imap4._FetchParser()
        self.assertRaises(Exception, p.parseString, b"BODY[HEADER")
        p = imap4._FetchParser()
        self.assertRaises(Exception, p.parseString, b"BODY[HEADER.FIELDS (SUBJECT)")

    def test_fetchParserHeaderMissingParentheses(self):
        """
        Parsing a C{BODY} whose C{HEADER.FIELDS} list does not begin
        with an open parenthesis (C{(}) or end with a close
        parenthesis (C{)}) raises an L{Exception}.
        """
        p = imap4._FetchParser()
        self.assertRaises(Exception, p.parseString, b"BODY[HEADER.FIELDS Missing)]")
        p = imap4._FetchParser()
        self.assertRaises(Exception, p.parseString, b"BODY[HEADER.FIELDS (Missing]")

    def test_fetchParserDotlessPartial(self):
        """
        Parsing a C{BODY} with a range that lacks a period (C{.})
        raises an L{Exception}.
        """
        p = imap4._FetchParser()
        self.assertRaises(Exception, p.parseString, b"BODY<01>")

    def test_fetchParserUnclosedPartial(self):
        """
        Parsing a C{BODY} with a partial range that's missing its
        closing greater than sign (C{>}) raises an L{EXCEPTION}.
        """
        p = imap4._FetchParser()
        self.assertRaises(Exception, p.parseString, b"BODY<0")

    def test_files(self):
        inputStructure = [
            "foo",
            "bar",
            "baz",
            BytesIO(b"this is a file\r\n"),
            "buz",
            "biz",
        ]

        output = b'"foo" "bar" "baz" {16}\r\nthis is a file\r\n "buz" "biz"'

        self.assertEqual(imap4.collapseNestedLists(inputStructure), output)

    def test_quoteAvoider(self):
        input = [
            b"foo",
            imap4.DontQuoteMe(b"bar"),
            b"baz",
            BytesIO(b"this is a file\r\n"),
            b"this is\r\nquoted",
            imap4.DontQuoteMe(b"buz"),
            b"",
        ]

        output = (
            b'"foo" bar "baz"'
            b" {16}\r\nthis is a file\r\n "
            b"{15}\r\nthis is\r\nquoted"
            b' buz ""'
        )

        self.assertEqual(imap4.collapseNestedLists(input), output)

    def test_literals(self):
        cases = [
            (b"({10}\r\n0123456789)", [[b"0123456789"]]),
        ]

        for (case, expected) in cases:
            self.assertEqual(imap4.parseNestedParens(case), expected)

    def test_queryBuilder(self):
        inputs = [
            imap4.Query(flagged=1),
            imap4.Query(sorted=1, unflagged=1, deleted=1),
            imap4.Or(imap4.Query(flagged=1), imap4.Query(deleted=1)),
            imap4.Query(before="today"),
            imap4.Or(imap4.Query(deleted=1), imap4.Query(unseen=1), imap4.Query(new=1)),
            imap4.Or(
                imap4.Not(
                    imap4.Or(
                        imap4.Query(sorted=1, since="yesterday", smaller=1000),
                        imap4.Query(sorted=1, before="tuesday", larger=10000),
                        imap4.Query(sorted=1, unseen=1, deleted=1, before="today"),
                        imap4.Not(imap4.Query(subject="spam")),
                    ),
                ),
                imap4.Not(imap4.Query(uid="1:5")),
            ),
        ]

        outputs = [
            "FLAGGED",
            "(DELETED UNFLAGGED)",
            "(OR FLAGGED DELETED)",
            '(BEFORE "today")',
            "(OR DELETED (OR UNSEEN NEW))",
            '(OR (NOT (OR (SINCE "yesterday" SMALLER 1000) '  # Continuing
            '(OR (BEFORE "tuesday" LARGER 10000) (OR (BEFORE '  # Some more
            '"today" DELETED UNSEEN) (NOT (SUBJECT "spam")))))) '  # And more
            "(NOT (UID 1:5)))",
        ]

        for (query, expected) in zip(inputs, outputs):
            self.assertEqual(query, expected)

    def test_queryKeywordFlagWithQuotes(self):
        """
        When passed the C{keyword} argument, L{imap4.Query} returns an unquoted
        string.

        @see: U{http://tools.ietf.org/html/rfc3501#section-9}
        @see: U{http://tools.ietf.org/html/rfc3501#section-6.4.4}
        """
        query = imap4.Query(keyword="twisted")
        self.assertEqual("(KEYWORD twisted)", query)

    def test_queryUnkeywordFlagWithQuotes(self):
        """
        When passed the C{unkeyword} argument, L{imap4.Query} returns an
        unquoted string.

        @see: U{http://tools.ietf.org/html/rfc3501#section-9}
        @see: U{http://tools.ietf.org/html/rfc3501#section-6.4.4}
        """
        query = imap4.Query(unkeyword="twisted")
        self.assertEqual("(UNKEYWORD twisted)", query)

    def test_queryWithMesssageSet(self):
        """
        When passed a L{MessageSet}, L{imap4.Query} returns a query
        containing a quoted string representing the ID sequence.
        """
        query = imap4.Query(messages=imap4.MessageSet(1, None))
        self.assertEqual(query, '(MESSAGES "1:*")')

    def test_queryWithInteger(self):
        """
        When passed an L{int}, L{imap4.Query} returns a query
        containing a quoted integer.
        """
        query = imap4.Query(messages=1)
        self.assertEqual(query, '(MESSAGES "1")')

    def test_queryOrIllegalQuery(self):
        """
        An L{imap4.Or} query with less than two arguments raises an
        L{imap4.IllegalQueryError}.
        """
        self.assertRaises(imap4.IllegalQueryError, imap4.Or, imap4.Query(messages=1))

    def _keywordFilteringTest(self, keyword):
        """
        Helper to implement tests for value filtering of KEYWORD and UNKEYWORD
        queries.

        @param keyword: A native string giving the name of the L{imap4.Query}
            keyword argument to test.
        """
        # Check all the printable exclusions
        self.assertEqual(
            f"({keyword.upper()} twistedrocks)",
            imap4.Query(**{keyword: r'twisted (){%*"\] rocks'}),
        )

        # Check all the non-printable exclusions
        self.assertEqual(
            f"({keyword.upper()} twistedrocks)",
            imap4.Query(
                **{
                    keyword: "twisted %s rocks"
                    % ("".join(chr(ch) for ch in range(33)),)
                }
            ),
        )

    def test_queryKeywordFlag(self):
        r"""
        When passed the C{keyword} argument, L{imap4.Query} returns an
        C{atom} that consists of one or more non-special characters.

        List of the invalid characters:

            ( ) { % * " \ ] CTL SP

        @see: U{ABNF definition of CTL and SP<https://tools.ietf.org/html/rfc2234>}
        @see: U{IMAP4 grammar<http://tools.ietf.org/html/rfc3501#section-9>}
        @see: U{IMAP4 SEARCH specification<http://tools.ietf.org/html/rfc3501#section-6.4.4>}
        """
        self._keywordFilteringTest("keyword")

    def test_queryUnkeywordFlag(self):
        r"""
        When passed the C{unkeyword} argument, L{imap4.Query} returns an
        C{atom} that consists of one or more non-special characters.

        List of the invalid characters:

            ( ) { % * " \ ] CTL SP

        @see: U{ABNF definition of CTL and SP<https://tools.ietf.org/html/rfc2234>}
        @see: U{IMAP4 grammar<http://tools.ietf.org/html/rfc3501#section-9>}
        @see: U{IMAP4 SEARCH specification<http://tools.ietf.org/html/rfc3501#section-6.4.4>}
        """
        self._keywordFilteringTest("unkeyword")

    def test_invalidIdListParser(self):
        """
        Trying to parse an invalid representation of a sequence range raises an
        L{IllegalIdentifierError}.
        """
        inputs = [b"*:*", b"foo", b"4:", b"bar:5"]

        for input in inputs:
            self.assertRaises(
                imap4.IllegalIdentifierError, imap4.parseIdList, input, 12345
            )

    def test_invalidIdListParserNonPositive(self):
        """
        Zeroes and negative values are not accepted in id range expressions. RFC
        3501 states that sequence numbers and sequence ranges consist of
        non-negative numbers (RFC 3501 section 9, the seq-number grammar item).
        """
        inputs = [b"0:5", b"0:0", b"*:0", b"0", b"-3:5", b"1:-2", b"-1"]

        for input in inputs:
            self.assertRaises(
                imap4.IllegalIdentifierError, imap4.parseIdList, input, 12345
            )

    def test_parseIdList(self):
        """
        The function to parse sequence ranges yields appropriate L{MessageSet}
        objects.
        """
        inputs = [
            b"1:*",
            b"5:*",
            b"1:2,5:*",
            b"*",
            b"1",
            b"1,2",
            b"1,3,5",
            b"1:10",
            b"1:10,11",
            b"1:5,10:20",
            b"1,5:10",
            b"1,5:10,15:20",
            b"1:10,15,20:25",
            b"4:2",
        ]

        outputs = [
            MessageSet(1, None),
            MessageSet(5, None),
            MessageSet(5, None) + MessageSet(1, 2),
            MessageSet(None, None),
            MessageSet(1),
            MessageSet(1, 2),
            MessageSet(1) + MessageSet(3) + MessageSet(5),
            MessageSet(1, 10),
            MessageSet(1, 11),
            MessageSet(1, 5) + MessageSet(10, 20),
            MessageSet(1) + MessageSet(5, 10),
            MessageSet(1) + MessageSet(5, 10) + MessageSet(15, 20),
            MessageSet(1, 10) + MessageSet(15) + MessageSet(20, 25),
            MessageSet(2, 4),
        ]

        lengths = [None, None, None, 1, 1, 2, 3, 10, 11, 16, 7, 13, 17, 3]

        for (input, expected) in zip(inputs, outputs):
            self.assertEqual(imap4.parseIdList(input), expected)

        for (input, expected) in zip(inputs, lengths):
            if expected is None:
                self.assertRaises(TypeError, len, imap4.parseIdList(input))
            else:
                L = len(imap4.parseIdList(input))
                self.assertEqual(L, expected, f"len({input!r}) = {L!r} != {expected!r}")

    def test_parseTimeInvalidFormat(self):
        """
        L{imap4.parseTime} raises L{ValueError} when given a a time
        string whose format is invalid.
        """
        self.assertRaises(ValueError, imap4.parseTime, "invalid")

    def test_parseTimeInvalidValues(self):
        """
        L{imap4.parseTime} raises L{ValueError} when given a time
        string composed of invalid values.
        """
        invalidStrings = [
            "invalid-July-2017",
            "2-invalid-2017",
            "2-July-invalid",
        ]
        for invalid in invalidStrings:
            self.assertRaises(ValueError, imap4.parseTime, invalid)

    def test_statusRequestHelper(self):
        """
        L{imap4.statusRequestHelper} builds a L{dict} mapping the
        requested status names to values extracted from the provided
        L{IMailboxIMAP}'s.
        """
        mbox = SimpleMailbox()

        expected = {
            "MESSAGES": mbox.getMessageCount(),
            "RECENT": mbox.getRecentCount(),
            "UIDNEXT": mbox.getUIDNext(),
            "UIDVALIDITY": mbox.getUIDValidity(),
            "UNSEEN": mbox.getUnseenCount(),
        }

        result = imap4.statusRequestHelper(mbox, expected.keys())

        self.assertEqual(expected, result)


@implementer(imap4.IMailboxInfo, imap4.IMailbox, imap4.ICloseableMailbox)
class SimpleMailbox:
    flags = ("\\Flag1", "Flag2", "\\AnotherSysFlag", "LastFlag")
    messages: List[Tuple[bytes, list, bytes, int]] = []
    mUID = 0
    rw = 1
    closed = False

    def __init__(self):
        self.listeners = []
        self.addListener = self.listeners.append
        self.removeListener = self.listeners.remove

    def getFlags(self):
        return self.flags

    def getUIDValidity(self):
        return 42

    def getUIDNext(self):
        return len(self.messages) + 1

    def getMessageCount(self):
        return 9

    def getRecentCount(self):
        return 3

    def getUnseenCount(self):
        return 4

    def isWriteable(self):
        return self.rw

    def destroy(self):
        pass

    def getHierarchicalDelimiter(self):
        return "/"

    def requestStatus(self, names):
        r = {}
        if "MESSAGES" in names:
            r["MESSAGES"] = self.getMessageCount()
        if "RECENT" in names:
            r["RECENT"] = self.getRecentCount()
        if "UIDNEXT" in names:
            r["UIDNEXT"] = self.getMessageCount() + 1
        if "UIDVALIDITY" in names:
            r["UIDVALIDITY"] = self.getUID()
        if "UNSEEN" in names:
            r["UNSEEN"] = self.getUnseenCount()
        return defer.succeed(r)

    def addMessage(self, message, flags, date=None):
        self.messages.append((message, flags, date, self.mUID))
        self.mUID += 1
        return defer.succeed(None)

    def expunge(self):
        delete = []
        for i in self.messages:
            if "\\Deleted" in i[1]:
                delete.append(i)
        for i in delete:
            self.messages.remove(i)
        return [i[3] for i in delete]

    def close(self):
        self.closed = True

    def fetch(self, messages, uid):
        # IMailboxIMAP.fetch
        pass

    def getUID(self, message):
        # IMailboxIMAP.getUID
        pass

    def store(self, messages, flags, mode, uid):
        # IMailboxIMAP.store
        pass


@implementer(imap4.IMailboxInfo, imap4.IMailbox)
class UncloseableMailbox:
    """
    A mailbox that cannot be closed.
    """

    flags = ("\\Flag1", "Flag2", "\\AnotherSysFlag", "LastFlag")
    messages: List[Tuple[bytes, list, bytes, int]] = []
    mUID = 0
    rw = 1
    closed = False

    def __init__(self):
        self.listeners = []
        self.addListener = self.listeners.append
        self.removeListener = self.listeners.remove

    def getFlags(self):
        """
        The flags

        @return: A sequence of flags.
        """
        return self.flags

    def getUIDValidity(self):
        """
        The UID validity value.

        @return: The value.
        """
        return 42

    def getUIDNext(self):
        """
        The next UID.

        @return: The UID.
        """
        return len(self.messages) + 1

    def getMessageCount(self):
        """
        The number of messages.

        @return: The number.
        """
        return 9

    def getRecentCount(self):
        """
        The recent messages.

        @return: The number.
        """
        return 3

    def getUnseenCount(self):
        """
        The recent messages.

        @return: The number.
        """
        return 4

    def isWriteable(self):
        """
        The recent messages.

        @return: Whether or not the mailbox is writable.
        """
        return self.rw

    def destroy(self):
        """
        Destroy this mailbox.
        """
        pass

    def getHierarchicalDelimiter(self):
        """
        Return the hierarchical delimiter.

        @return: The delimiter.
        """
        return "/"

    def requestStatus(self, names):
        """
        Return the mailbox's status.

        @param names: The status items to include.

        @return: A L{dict} of status data.
        """
        r = {}
        if "MESSAGES" in names:
            r["MESSAGES"] = self.getMessageCount()
        if "RECENT" in names:
            r["RECENT"] = self.getRecentCount()
        if "UIDNEXT" in names:
            r["UIDNEXT"] = self.getMessageCount() + 1
        if "UIDVALIDITY" in names:
            r["UIDVALIDITY"] = self.getUID()
        if "UNSEEN" in names:
            r["UNSEEN"] = self.getUnseenCount()
        return defer.succeed(r)

    def addMessage(self, message, flags, date=None):
        """
        Add a message to the mailbox.

        @param message: The message body.

        @param flags: The message flags.

        @param date: The message date.

        @return: A L{Deferred} that fires when the message has been
            added.
        """
        self.messages.append((message, flags, date, self.mUID))
        self.mUID += 1
        return defer.succeed(None)

    def expunge(self):
        """
        Delete messages marked for deletion.

        @return: A L{list} of deleted message IDs.
        """
        delete = []
        for i in self.messages:
            if "\\Deleted" in i[1]:
                delete.append(i)
        for i in delete:
            self.messages.remove(i)
        return [i[3] for i in delete]

    def fetch(self, messages, uid):
        # IMailboxIMAP.fetch
        pass

    def getUID(self, message):
        # IMailboxIMAP.getUID
        pass

    def store(self, messages, flags, mode, uid):
        # IMailboxIMAP.store
        pass


class AccountWithoutNamespaces(imap4.MemoryAccountWithoutNamespaces):
    """
    An in-memory account that does not provide L{INamespacePresenter}.
    """

    mailboxFactory = SimpleMailbox

    def _emptyMailbox(self, name, id):
        return self.mailboxFactory()

    def select(self, name, rw=1):
        mbox = imap4.MemoryAccount.select(self, name)
        if mbox is not None:
            mbox.rw = rw
        return mbox


class Account(AccountWithoutNamespaces, imap4.MemoryAccount):
    """
    An in-memory account that provides L{INamespacePresenter}.
    """


class SimpleServer(imap4.IMAP4Server):
    theAccount = Account(b"testuser")

    def __init__(self, *args, **kw):
        imap4.IMAP4Server.__init__(self, *args, **kw)
        realm = TestRealm(accountHolder=self)
        portal = Portal(realm)
        c = InMemoryUsernamePasswordDatabaseDontUse()
        c.addUser(b"testuser", b"password-test")
        self.checker = c
        self.portal = portal
        portal.registerChecker(c)
        self.timeoutTest = False

    def lineReceived(self, line):
        if self.timeoutTest:
            # Do not send a response
            return

        imap4.IMAP4Server.lineReceived(self, line)


class SimpleClient(imap4.IMAP4Client):
    def __init__(self, deferred, contextFactory=None):
        imap4.IMAP4Client.__init__(self, contextFactory)
        self.deferred = deferred
        self.events = []

    def serverGreeting(self, caps):
        self.deferred.callback(None)

    def modeChanged(self, writeable):
        self.events.append(["modeChanged", writeable])
        self.transport.loseConnection()

    def flagsChanged(self, newFlags):
        self.events.append(["flagsChanged", newFlags])
        self.transport.loseConnection()

    def newMessages(self, exists, recent):
        self.events.append(["newMessages", exists, recent])
        self.transport.loseConnection()


class IMAP4HelperMixin:

    serverCTX: Optional[ServerTLSContext] = None
    clientCTX: Optional[ClientTLSContext] = None

    def setUp(self):
        d = defer.Deferred()
        self.server = SimpleServer(contextFactory=self.serverCTX)
        self.client = SimpleClient(d, contextFactory=self.clientCTX)
        self.connected = d

        SimpleMailbox.messages = []
        theAccount = Account(b"testuser")
        theAccount.mboxType = SimpleMailbox
        SimpleServer.theAccount = theAccount

    def tearDown(self):
        del self.server
        del self.client
        del self.connected

    def _cbStopClient(self, ignore):
        self.client.transport.loseConnection()

    def _ebGeneral(self, failure):
        self.client.transport.loseConnection()
        self.server.transport.loseConnection()
        log.err(failure, "Problem with " + str(self))

    def loopback(self):
        return loopback.loopbackAsync(self.server, self.client)

    def assertClientFailureMessage(self, failure, expected):
        """
        Assert that the provided failure is an L{IMAP4Exception} with
        the given message.

        @param failure: A failure whose value L{IMAP4Exception}
        @type failure: L{failure.Failure}

        @param expected: The expected failure message.
        @type expected: L{bytes}
        """
        failure.trap(imap4.IMAP4Exception)
        message = str(failure.value)
        expected = repr(expected)

        self.assertEqual(message, expected)


class IMAP4ServerTests(IMAP4HelperMixin, TestCase):
    def testCapability(self):
        caps = {}

        def getCaps():
            def gotCaps(c):
                caps.update(c)
                self.server.transport.loseConnection()

            return self.client.getCapabilities().addCallback(gotCaps)

        d1 = self.connected.addCallback(strip(getCaps)).addErrback(self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        expected = {b"IMAP4rev1": None, b"NAMESPACE": None, b"IDLE": None}
        return d.addCallback(lambda _: self.assertEqual(expected, caps))

    def testCapabilityWithAuth(self):
        caps = {}
        self.server.challengers[b"CRAM-MD5"] = CramMD5Credentials

        def getCaps():
            def gotCaps(c):
                caps.update(c)
                self.server.transport.loseConnection()

            return self.client.getCapabilities().addCallback(gotCaps)

        d1 = self.connected.addCallback(strip(getCaps)).addErrback(self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])

        expCap = {
            b"IMAP4rev1": None,
            b"NAMESPACE": None,
            b"IDLE": None,
            b"AUTH": [b"CRAM-MD5"],
        }

        return d.addCallback(lambda _: self.assertEqual(expCap, caps))

    def testLogout(self):
        self.loggedOut = 0

        def logout():
            def setLoggedOut():
                self.loggedOut = 1

            self.client.logout().addCallback(strip(setLoggedOut))

        self.connected.addCallback(strip(logout)).addErrback(self._ebGeneral)
        d = self.loopback()
        return d.addCallback(lambda _: self.assertEqual(self.loggedOut, 1))

    def testNoop(self):
        self.responses = None

        def noop():
            def setResponses(responses):
                self.responses = responses
                self.server.transport.loseConnection()

            self.client.noop().addCallback(setResponses)

        self.connected.addCallback(strip(noop)).addErrback(self._ebGeneral)
        d = self.loopback()
        return d.addCallback(lambda _: self.assertEqual(self.responses, []))

    def testLogin(self):
        def login():
            d = self.client.login(b"testuser", b"password-test")
            d.addCallback(self._cbStopClient)

        d1 = self.connected.addCallback(strip(login)).addErrback(self._ebGeneral)
        d = defer.gatherResults([d1, self.loopback()])
        return d.addCallback(self._cbTestLogin)

    def _cbTestLogin(self, ignored):
        self.assertEqual(self.server.account, SimpleServer.theAccount)
        self.assertEqual(self.server.state, "auth")

    def testFailedLogin(self):
        def login():
            d = self.client.login(b"testuser", b"wrong-password")
            d.addBoth(self._cbStopClient)

        d1 = self.connected.addCallback(strip(login)).addErrback(self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        return d.addCallback(self._cbTestFailedLogin)

    def _cbTestFailedLogin(self, ignored):
        self.assertEqual(self.server.account, None)
        self.assertEqual(self.server.state, "unauth")

    def test_loginWithoutPortal(self):
        """
        Attempting to log into a server that has no L{Portal} results
        in a failed login.
        """
        self.server.portal = None

        def login():
            d = self.client.login(b"testuser", b"wrong-password")
            d.addBoth(self._cbStopClient)

        d1 = self.connected.addCallback(strip(login)).addErrback(self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        return d.addCallback(self._cbTestFailedLogin)

    def test_nonIAccountAvatar(self):
        """
        The server responds with a C{BAD} response when its portal
        attempts to log a user in with checker that claims to support
        L{IAccount} but returns an an avatar interface that is not
        L{IAccount}.
        """

        def brokenRequestAvatar(*_, **__):
            return ("Not IAccount", "Not an account", lambda: None)

        self.server.portal.realm.requestAvatar = brokenRequestAvatar

        def login():
            d = self.client.login(b"testuser", b"password-test")
            d.addBoth(self._cbStopClient)

        d1 = self.connected.addCallback(strip(login)).addErrback(self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        return d.addCallback(self._cbTestFailedLogin)

    def test_loginException(self):
        """
        Any exception raised by L{IMAP4Server.authenticateLogin} that
        is not L{UnauthorizedLogin} is logged results in a C{BAD}
        response.
        """

        class UnexpectedException(Exception):
            """
            An unexpected exception.
            """

        def raisesUnexpectedException(user, passwd):
            raise UnexpectedException("Whoops")

        self.server.authenticateLogin = raisesUnexpectedException

        def login():
            return self.client.login(b"testuser", b"password-test")

        d1 = self.connected.addCallback(strip(login))

        d1.addErrback(self.assertClientFailureMessage, b"Server error: Whoops")

        @d1.addCallback
        def assertErrorLogged(_):
            self.assertTrue(self.flushLoggedErrors(UnexpectedException))

        d1.addErrback(self._ebGeneral)
        d1.addBoth(self._cbStopClient)

        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        return d.addCallback(self._cbTestFailedLogin)

    def testLoginRequiringQuoting(self):
        self.server.checker.users = {b"{test}user": b"{test}password"}

        def login():
            d = self.client.login(b"{test}user", b"{test}password")
            d.addErrback(log.err, "Problem with " + str(self))
            d.addCallback(self._cbStopClient)

        d1 = self.connected.addCallback(strip(login)).addErrback(self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d.addCallback(self._cbTestLoginRequiringQuoting)

    def _cbTestLoginRequiringQuoting(self, ignored):
        self.assertEqual(self.server.account, SimpleServer.theAccount)
        self.assertEqual(self.server.state, "auth")

    def testNamespace(self):
        self.namespaceArgs = None

        def login():
            return self.client.login(b"testuser", b"password-test")

        def namespace():
            def gotNamespace(args):
                self.namespaceArgs = args
                self._cbStopClient(None)

            return self.client.namespace().addCallback(gotNamespace)

        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(namespace))
        d1.addErrback(self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])

        @d.addCallback
        def assertAllPairsNativeStrings(ignored):
            for namespaces in self.namespaceArgs:
                for pair in namespaces:
                    for value in pair:
                        self.assertIsInstance(value, str)
            return self.namespaceArgs

        d.addCallback(self.assertEqual, [[["", "/"]], [], []])
        return d

    def test_mailboxWithoutNamespace(self):
        """
        A mailbox that does not provide L{INamespacePresenter} returns
        empty L{list}s for its personal, shared, and user namespaces.
        """
        self.server.theAccount = AccountWithoutNamespaces(b"testuser")
        self.namespaceArgs = None

        def login():
            return self.client.login(b"testuser", b"password-test")

        def namespace():
            def gotNamespace(args):
                self.namespaceArgs = args
                self._cbStopClient(None)

            return self.client.namespace().addCallback(gotNamespace)

        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(namespace))
        d1.addErrback(self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        d.addCallback(lambda _: self.namespaceArgs)
        d.addCallback(self.assertEqual, [[], [], []])
        return d

    def testSelect(self):
        SimpleServer.theAccount.addMailbox("test-mailbox")
        self.selectedArgs = None

        def login():
            return self.client.login(b"testuser", b"password-test")

        def select():
            def selected(args):
                self.selectedArgs = args
                self._cbStopClient(None)

            d = self.client.select("test-mailbox")
            d.addCallback(selected)
            return d

        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(select))
        d1.addErrback(self._ebGeneral)
        d2 = self.loopback()
        return defer.gatherResults([d1, d2]).addCallback(self._cbTestSelect)

    def test_selectWithoutMailbox(self):
        """
        A client that selects a mailbox that does not exist receives a
        C{NO} response.
        """

        def login():
            return self.client.login(b"testuser", b"password-test")

        def select():
            return self.client.select("test-mailbox")

        self.connected.addCallback(strip(login))
        self.connected.addCallback(strip(select))
        self.connected.addErrback(self.assertClientFailureMessage, b"No such mailbox")
        self.connected.addCallback(self._cbStopClient)
        self.connected.addErrback(self._ebGeneral)

        connectionComplete = defer.gatherResults([self.connected, self.loopback()])

        @connectionComplete.addCallback
        def assertNoMailboxSelected(_):
            self.assertIsNone(self.server.mbox)

        return connectionComplete

    def _cbTestSelect(self, ignored):
        mbox = SimpleServer.theAccount.mailboxes["TEST-MAILBOX"]
        self.assertEqual(self.server.mbox, mbox)
        self.assertEqual(
            self.selectedArgs,
            {
                "EXISTS": 9,
                "RECENT": 3,
                "UIDVALIDITY": 42,
                "FLAGS": ("\\Flag1", "Flag2", "\\AnotherSysFlag", "LastFlag"),
                "READ-WRITE": True,
            },
        )

    def test_examine(self):
        """
        L{IMAP4Client.examine} issues an I{EXAMINE} command to the server and
        returns a L{Deferred} which fires with a C{dict} with as many of the
        following keys as the server includes in its response: C{'FLAGS'},
        C{'EXISTS'}, C{'RECENT'}, C{'UNSEEN'}, C{'READ-WRITE'}, C{'READ-ONLY'},
        C{'UIDVALIDITY'}, and C{'PERMANENTFLAGS'}.

        Unfortunately the server doesn't generate all of these so it's hard to
        test the client's handling of them here.  See
        L{IMAP4ClientExamineTests} below.

        See U{RFC 3501<http://www.faqs.org/rfcs/rfc3501.html>}, section 6.3.2,
        for details.
        """
        SimpleServer.theAccount.addMailbox("test-mailbox")
        self.examinedArgs = None

        def login():
            return self.client.login(b"testuser", b"password-test")

        def examine():
            def examined(args):
                self.examinedArgs = args
                self._cbStopClient(None)

            d = self.client.examine("test-mailbox")
            d.addCallback(examined)
            return d

        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(examine))
        d1.addErrback(self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        return d.addCallback(self._cbTestExamine)

    def _cbTestExamine(self, ignored):
        mbox = SimpleServer.theAccount.mailboxes["TEST-MAILBOX"]
        self.assertEqual(self.server.mbox, mbox)
        self.assertEqual(
            self.examinedArgs,
            {
                "EXISTS": 9,
                "RECENT": 3,
                "UIDVALIDITY": 42,
                "FLAGS": ("\\Flag1", "Flag2", "\\AnotherSysFlag", "LastFlag"),
                "READ-WRITE": False,
            },
        )

    def testCreate(self):
        succeed = ("testbox", "test/box", "test/", "test/box/box", "INBOX")
        fail = ("testbox", "test/box")

        def cb():
            self.result.append(1)

        def eb(failure):
            self.result.append(0)

        def login():
            return self.client.login(b"testuser", b"password-test")

        def create():
            for name in succeed + fail:
                d = self.client.create(name)
                d.addCallback(strip(cb)).addErrback(eb)
            d.addCallbacks(self._cbStopClient, self._ebGeneral)

        self.result = []
        d1 = self.connected.addCallback(strip(login)).addCallback(strip(create))
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        return d.addCallback(self._cbTestCreate, succeed, fail)

    def _cbTestCreate(self, ignored, succeed, fail):
        self.assertEqual(self.result, [1] * len(succeed) + [0] * len(fail))
        mbox = sorted(SimpleServer.theAccount.mailboxes)
        answers = sorted(["inbox", "testbox", "test/box", "test", "test/box/box"])
        self.assertEqual(mbox, [a.upper() for a in answers])

    def testDelete(self):
        SimpleServer.theAccount.addMailbox("delete/me")

        def login():
            return self.client.login(b"testuser", b"password-test")

        def delete():
            return self.client.delete("delete/me")

        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(delete), self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        d.addCallback(
            lambda _: self.assertEqual(list(SimpleServer.theAccount.mailboxes), [])
        )
        return d

    def testDeleteWithInferiorHierarchicalNames(self):
        """
        Attempting to delete a mailbox with hierarchically inferior
        names fails with an informative error.

        @see: U{https://tools.ietf.org/html/rfc3501#section-6.3.4}

        @return: A L{Deferred} with assertions.
        """
        SimpleServer.theAccount.addMailbox("delete")
        SimpleServer.theAccount.addMailbox("delete/me")

        def login():
            return self.client.login(b"testuser", b"password-test")

        def delete():
            return self.client.delete("delete")

        def assertIMAPException(failure):
            failure.trap(imap4.IMAP4Exception)
            self.assertEqual(
                str(failure.value),
                str(b'Name "DELETE" has inferior hierarchical names'),
            )

        loggedIn = self.connected.addCallback(strip(login))
        loggedIn.addCallbacks(strip(delete), self._ebGeneral)
        loggedIn.addErrback(assertIMAPException)
        loggedIn.addCallbacks(self._cbStopClient)

        loopedBack = self.loopback()
        d = defer.gatherResults([loggedIn, loopedBack])
        d.addCallback(
            lambda _: self.assertEqual(
                sorted(SimpleServer.theAccount.mailboxes), ["DELETE", "DELETE/ME"]
            )
        )
        return d

    def testIllegalInboxDelete(self):
        self.stashed = None

        def login():
            return self.client.login(b"testuser", b"password-test")

        def delete():
            return self.client.delete("inbox")

        def stash(result):
            self.stashed = result

        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(delete), self._ebGeneral)
        d1.addBoth(stash)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        d.addCallback(
            lambda _: self.assertTrue(isinstance(self.stashed, failure.Failure))
        )
        return d

    def testNonExistentDelete(self):
        def login():
            return self.client.login(b"testuser", b"password-test")

        def delete():
            return self.client.delete("delete/me")

        def deleteFailed(failure):
            self.failure = failure

        self.failure = None
        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(delete)).addErrback(deleteFailed)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        d.addCallback(
            lambda _: self.assertEqual(str(self.failure.value), str(b"No such mailbox"))
        )
        return d

    def testIllegalDelete(self):
        m = SimpleMailbox()
        m.flags = (r"\Noselect",)
        SimpleServer.theAccount.addMailbox("delete", m)
        SimpleServer.theAccount.addMailbox("delete/me")

        def login():
            return self.client.login(b"testuser", b"password-test")

        def delete():
            return self.client.delete("delete")

        def deleteFailed(failure):
            self.failure = failure

        self.failure = None
        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(delete)).addErrback(deleteFailed)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        expected = str(
            b"Hierarchically inferior mailboxes exist " b"and \\Noselect is set"
        )
        d.addCallback(lambda _: self.assertEqual(str(self.failure.value), expected))
        return d

    def testRename(self):
        SimpleServer.theAccount.addMailbox("oldmbox")

        def login():
            return self.client.login(b"testuser", b"password-test")

        def rename():
            return self.client.rename(b"oldmbox", b"newname")

        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(rename), self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        d.addCallback(
            lambda _: self.assertEqual(
                list(SimpleServer.theAccount.mailboxes.keys()), ["NEWNAME"]
            )
        )
        return d

    def testIllegalInboxRename(self):
        self.stashed = None

        def login():
            return self.client.login(b"testuser", b"password-test")

        def rename():
            return self.client.rename("inbox", "frotz")

        def stash(stuff):
            self.stashed = stuff

        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(rename), self._ebGeneral)
        d1.addBoth(stash)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        d.addCallback(
            lambda _: self.assertTrue(isinstance(self.stashed, failure.Failure))
        )
        return d

    def testHierarchicalRename(self):
        SimpleServer.theAccount.create("oldmbox/m1")
        SimpleServer.theAccount.create("oldmbox/m2")

        def login():
            return self.client.login(b"testuser", b"password-test")

        def rename():
            return self.client.rename("oldmbox", "newname")

        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(rename), self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        return d.addCallback(self._cbTestHierarchicalRename)

    def _cbTestHierarchicalRename(self, ignored):
        mboxes = SimpleServer.theAccount.mailboxes.keys()
        expected = ["newname", "newname/m1", "newname/m2"]
        mboxes = list(sorted(mboxes))
        self.assertEqual(mboxes, [s.upper() for s in expected])

    def testSubscribe(self):
        def login():
            return self.client.login(b"testuser", b"password-test")

        def subscribe():
            return self.client.subscribe("this/mbox")

        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(subscribe), self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        d.addCallback(
            lambda _: self.assertEqual(
                SimpleServer.theAccount.subscriptions, ["THIS/MBOX"]
            )
        )
        return d

    def testUnsubscribe(self):
        SimpleServer.theAccount.subscriptions = ["THIS/MBOX", "THAT/MBOX"]

        def login():
            return self.client.login(b"testuser", b"password-test")

        def unsubscribe():
            return self.client.unsubscribe("this/mbox")

        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(unsubscribe), self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        d.addCallback(
            lambda _: self.assertEqual(
                SimpleServer.theAccount.subscriptions, ["THAT/MBOX"]
            )
        )
        return d

    def _listSetup(self, f):
        SimpleServer.theAccount.addMailbox("root/subthing")
        SimpleServer.theAccount.addMailbox("root/another-thing")
        SimpleServer.theAccount.addMailbox("non-root/subthing")

        def login():
            return self.client.login(b"testuser", b"password-test")

        def listed(answers):
            self.listed = answers

        self.listed = None
        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(f), self._ebGeneral)
        d1.addCallbacks(listed, self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        return defer.gatherResults([d1, d2]).addCallback(lambda _: self.listed)

    def assertListDelimiterAndMailboxAreStrings(self, results):
        """
        Assert a C{LIST} response's delimiter and mailbox are native
        strings.

        @param results: A list of tuples as returned by
            L{IMAP4Client.list} or L{IMAP4Client.lsub}.
        """
        for result in results:
            self.assertIsInstance(result[1], str, "delimiter %r is not a str")
            self.assertIsInstance(result[2], str, "mailbox %r is not a str")
        return results

    def testList(self):
        def mailboxList():
            return self.client.list("root", "%")

        d = self._listSetup(mailboxList)

        @d.addCallback
        def assertListContents(listed):
            expectedContents = [
                (sorted(SimpleMailbox.flags), "/", "ROOT/SUBTHING"),
                (sorted(SimpleMailbox.flags), "/", "ROOT/ANOTHER-THING"),
            ]

            for _ in range(2):
                flags, delimiter, mailbox = listed.pop(0)
                self.assertIn(
                    (sorted(flags), delimiter, mailbox),
                    expectedContents,
                )

            self.assertFalse(listed, f"More results than expected: {listed!r}")

        return d

    def testLSub(self):
        SimpleServer.theAccount.subscribe("ROOT/SUBTHING")

        def lsub():
            return self.client.lsub("root", "%")

        d = self._listSetup(lsub)
        d.addCallback(self.assertListDelimiterAndMailboxAreStrings)
        d.addCallback(self.assertEqual, [(SimpleMailbox.flags, "/", "ROOT/SUBTHING")])
        return d

    def testStatus(self):
        SimpleServer.theAccount.addMailbox("root/subthing")

        def login():
            return self.client.login(b"testuser", b"password-test")

        def status():
            return self.client.status("root/subthing", "MESSAGES", "UIDNEXT", "UNSEEN")

        def statused(result):
            self.statused = result

        self.statused = None
        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(status), self._ebGeneral)
        d1.addCallbacks(statused, self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        d.addCallback(
            lambda _: self.assertEqual(
                self.statused, {"MESSAGES": 9, "UIDNEXT": b"10", "UNSEEN": 4}
            )
        )
        return d

    def testFailedStatus(self):
        def login():
            return self.client.login(b"testuser", b"password-test")

        def status():
            return self.client.status(
                "root/nonexistent", "MESSAGES", "UIDNEXT", "UNSEEN"
            )

        def statused(result):
            self.statused = result

        def failed(failure):
            self.failure = failure

        self.statused = self.failure = None
        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(status), self._ebGeneral)
        d1.addCallbacks(statused, failed)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        return defer.gatherResults([d1, d2]).addCallback(self._cbTestFailedStatus)

    def _cbTestFailedStatus(self, ignored):
        self.assertEqual(self.statused, None)
        self.assertEqual(self.failure.value.args, (b"Could not open mailbox",))

    def testFullAppend(self):
        infile = util.sibpath(__file__, "rfc822.message")
        SimpleServer.theAccount.addMailbox("root/subthing")

        def login():
            return self.client.login(b"testuser", b"password-test")

        @defer.inlineCallbacks
        def append():
            with open(infile, "rb") as message:
                result = yield self.client.append(
                    "root/subthing",
                    message,
                    ("\\SEEN", "\\DELETED"),
                    "Tue, 17 Jun 2003 11:22:16 -0600 (MDT)",
                )
                defer.returnValue(result)

        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(append), self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()

        d = defer.gatherResults([d1, d2])

        return d.addCallback(self._cbTestFullAppend, infile)

    def _cbTestFullAppend(self, ignored, infile):
        mb = SimpleServer.theAccount.mailboxes["ROOT/SUBTHING"]
        self.assertEqual(1, len(mb.messages))
        self.assertEqual(
            (["\\SEEN", "\\DELETED"], b"Tue, 17 Jun 2003 11:22:16 -0600 (MDT)", 0),
            mb.messages[0][1:],
        )
        with open(infile, "rb") as f:
            self.assertEqual(f.read(), mb.messages[0][0].getvalue())

    def testPartialAppend(self):
        infile = util.sibpath(__file__, "rfc822.message")
        SimpleServer.theAccount.addMailbox("PARTIAL/SUBTHING")

        def login():
            return self.client.login(b"testuser", b"password-test")

        @defer.inlineCallbacks
        def append():
            with open(infile, "rb") as message:
                result = yield self.client.sendCommand(
                    imap4.Command(
                        b"APPEND",
                        # Using networkString is cheating!  In this
                        # particular case the mailbox name happens to
                        # be ASCII.  In real code, the mailbox would
                        # be encoded with imap4-utf-7.
                        networkString(
                            "PARTIAL/SUBTHING "
                            '(\\SEEN) "Right now" '
                            "{%d}" % (os.path.getsize(infile),)
                        ),
                        (),
                        self.client._IMAP4Client__cbContinueAppend,
                        message,
                    )
                )
                defer.returnValue(result)

        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(append), self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        return d.addCallback(self._cbTestPartialAppend, infile)

    def _cbTestPartialAppend(self, ignored, infile):
        mb = SimpleServer.theAccount.mailboxes["PARTIAL/SUBTHING"]
        self.assertEqual(1, len(mb.messages))
        self.assertEqual((["\\SEEN"], b"Right now", 0), mb.messages[0][1:])
        with open(infile, "rb") as f:
            self.assertEqual(f.read(), mb.messages[0][0].getvalue())

    def _testCheck(self):
        SimpleServer.theAccount.addMailbox(b"root/subthing")

        def login():
            return self.client.login(b"testuser", b"password-test")

        def select():
            return self.client.select(b"root/subthing")

        def check():
            return self.client.check()

        d = self.connected.addCallback(strip(login))
        d.addCallbacks(strip(select), self._ebGeneral)
        d.addCallbacks(strip(check), self._ebGeneral)
        d.addCallbacks(self._cbStopClient, self._ebGeneral)
        return self.loopback()

    def test_check(self):
        """
        Trigger the L{imap.IMAP4Server._cbSelectWork} callback
        by selecting an mbox.
        """
        return self._testCheck()

    def test_checkFail(self):
        """
        Trigger the L{imap.IMAP4Server._ebSelectWork} errback
        by failing when we select an mbox.
        """

        def failSelect(self, name, rw=1):
            raise imap4.IllegalMailboxEncoding("encoding")

        def checkResponse(ignore):
            failures = self.flushLoggedErrors()
            self.assertEqual(failures[1].value.args[0], b"SELECT failed: Server error")

        self.patch(Account, "select", failSelect)
        d = self._testCheck()
        return d.addCallback(checkResponse)

    def testClose(self):
        m = SimpleMailbox()
        m.messages = [
            (b"Message 1", ("\\Deleted", "AnotherFlag"), None, 0),
            (b"Message 2", ("AnotherFlag",), None, 1),
            (b"Message 3", ("\\Deleted",), None, 2),
        ]
        SimpleServer.theAccount.addMailbox("mailbox", m)

        def login():
            return self.client.login(b"testuser", b"password-test")

        def select():
            return self.client.select(b"mailbox")

        def close():
            return self.client.close()

        d = self.connected.addCallback(strip(login))
        d.addCallbacks(strip(select), self._ebGeneral)
        d.addCallbacks(strip(close), self._ebGeneral)
        d.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        return defer.gatherResults([d, d2]).addCallback(self._cbTestClose, m)

    def _cbTestClose(self, ignored, m):
        self.assertEqual(len(m.messages), 1)
        self.assertEqual(m.messages[0], (b"Message 2", ("AnotherFlag",), None, 1))
        self.assertTrue(m.closed)

    def testExpunge(self):
        m = SimpleMailbox()
        m.messages = [
            (b"Message 1", ("\\Deleted", "AnotherFlag"), None, 0),
            (b"Message 2", ("AnotherFlag",), None, 1),
            (b"Message 3", ("\\Deleted",), None, 2),
        ]
        SimpleServer.theAccount.addMailbox("mailbox", m)

        def login():
            return self.client.login(b"testuser", b"password-test")

        def select():
            return self.client.select("mailbox")

        def expunge():
            return self.client.expunge()

        def expunged(results):
            self.assertFalse(self.server.mbox is None)
            self.results = results

        self.results = None
        d1 = self.connected.addCallback(strip(login))
        d1.addCallbacks(strip(select), self._ebGeneral)
        d1.addCallbacks(strip(expunge), self._ebGeneral)
        d1.addCallbacks(expunged, self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        return d.addCallback(self._cbTestExpunge, m)

    def _cbTestExpunge(self, ignored, m):
        self.assertEqual(len(m.messages), 1)
        self.assertEqual(m.messages[0], (b"Message 2", ("AnotherFlag",), None, 1))

        self.assertEqual(self.results, [0, 2])


class IMAP4ServerParsingTests(SynchronousTestCase):
    """
    Test L{imap4.IMAP4Server}'s command parsing.
    """

    def setUp(self):
        self.transport = StringTransport()
        self.server = imap4.IMAP4Server()
        self.server.makeConnection(self.transport)
        self.transport.clear()

    def tearDown(self):
        self.server.connectionLost(failure.Failure(error.ConnectionDone()))

    def test_parseMethodExceptionLogged(self):
        """
        L{imap4.IMAP4Server} logs exceptions raised by parse methods.
        """

        class UnhandledException(Exception):
            """
            An unhandled exception.
            """

        def raisesValueError(line):
            raise UnhandledException

        self.server.parseState = "command"
        self.server.parse_command = raisesValueError

        self.server.lineReceived(b"invalid")

        self.assertTrue(self.flushLoggedErrors(UnhandledException))

    def test_missingCommand(self):
        """
        L{imap4.IMAP4Server.parse_command} sends a C{BAD} response to
        a line that includes a tag but no command.
        """
        self.server.parse_command(b"001")

        self.assertEqual(self.transport.value(), b"001 BAD Missing command\r\n")

        self.server.connectionLost(
            failure.Failure(error.ConnectionDone("Done")),
        )

    def test_emptyLine(self):
        """
        L{imap4.IMAP4Server.parse_command} sends a C{BAD} response to
        an empty line.
        """
        self.server.parse_command(b"")

        self.assertEqual(self.transport.value(), b"* BAD Null command\r\n")

    def assertParseExceptionResponse(self, exception, tag, expectedResponse):
        """
        Assert that the given exception results in the expected
        response.

        @param exception: The exception to raise.
        @type exception: L{Exception}

        @param tag: The IMAP tag.

        @type: L{bytes}

        @param expectedResponse: The expected bad response.
        @type expectedResponse: L{bytes}
        """

        def raises(tag, cmd, rest):
            raise exception

        self.server.dispatchCommand = raises

        self.server.parse_command(b" ".join([tag, b"invalid"]))

        self.assertEqual(self.transport.value(), b" ".join([tag, expectedResponse]))

    def test_parsingRaisesIllegalClientResponse(self):
        """
        When a parsing method raises L{IllegalClientResponse}, the
        server sends a C{BAD} response.
        """
        self.assertParseExceptionResponse(
            imap4.IllegalClientResponse("client response"),
            b"001",
            b"BAD Illegal syntax: client response\r\n",
        )

    def test_parsingRaisesIllegalOperationResponse(self):
        """
        When a parsing method raises L{IllegalOperation}, the server
        sends a C{NO} response.
        """
        self.assertParseExceptionResponse(
            imap4.IllegalOperation("operation"),
            b"001",
            b"NO Illegal operation: operation\r\n",
        )

    def test_parsingRaisesIllegalMailboxEncoding(self):
        """
        When a parsing method raises L{IllegalMailboxEncoding}, the
        server sends a C{NO} response.
        """
        self.assertParseExceptionResponse(
            imap4.IllegalMailboxEncoding("encoding"),
            b"001",
            b"NO Illegal mailbox name: encoding\r\n",
        )

    def test_unsupportedCommand(self):
        """
        L{imap4.IMAP4Server} responds to an unsupported command with a
        C{BAD} response.
        """
        self.server.lineReceived(b"001 HULLABALOO")
        self.assertEqual(self.transport.value(), b"001 BAD Unsupported command\r\n")

    def test_tooManyArgumentsForCommand(self):
        """
        L{imap4.IMAP4Server} responds with a C{BAD} response to a
        command with more arguments than expected.
        """
        self.server.lineReceived(b"001 LOGIN A B C")
        self.assertEqual(
            self.transport.value(),
            (
                b"001 BAD Illegal syntax:"
                + b" Too many arguments for command: "
                + repr(b"C").encode("utf-8")
                + b"\r\n"
            ),
        )

    def assertCommandExceptionResponse(self, exception, tag, expectedResponse):
        """
        Assert that the given exception results in the expected
        response.

        @param exception: The exception to raise.
        @type exception: L{Exception}

        @param: The IMAP tag.

        @type: L{bytes}

        @param expectedResponse: The expected bad response.
        @type expectedResponse: L{bytes}
        """

        def raises(serverInstance, tag, user, passwd):
            raise exception

        self.assertEqual(self.server.state, "unauth")

        self.server.unauth_LOGIN = (raises,) + self.server.unauth_LOGIN[1:]

        self.server.dispatchCommand(tag, b"LOGIN", b"user passwd")

        self.assertEqual(self.transport.value(), b" ".join([tag, expectedResponse]))

    def test_commandRaisesIllegalClientResponse(self):
        """
        When a command raises L{IllegalClientResponse}, the
        server sends a C{BAD} response.
        """
        self.assertCommandExceptionResponse(
            imap4.IllegalClientResponse("client response"),
            b"001",
            b"BAD Illegal syntax: client response\r\n",
        )

    def test_commandRaisesIllegalOperationResponse(self):
        """
        When a command raises L{IllegalOperation}, the server sends a
        C{NO} response.
        """
        self.assertCommandExceptionResponse(
            imap4.IllegalOperation("operation"),
            b"001",
            b"NO Illegal operation: operation\r\n",
        )

    def test_commandRaisesIllegalMailboxEncoding(self):
        """
        When a command raises L{IllegalMailboxEncoding}, the server
        sends a C{NO} response.
        """
        self.assertCommandExceptionResponse(
            imap4.IllegalMailboxEncoding("encoding"),
            b"001",
            b"NO Illegal mailbox name: encoding\r\n",
        )

    def test_commandRaisesUnhandledException(self):
        """
        Wehn a command raises an unhandled exception, the server sends
        a C{BAD} response and logs the exception.
        """

        class UnhandledException(Exception):
            """
            An unhandled exception.
            """

        self.assertCommandExceptionResponse(
            UnhandledException("unhandled"),
            b"001",
            b"BAD Server error: unhandled\r\n",
        )

        self.assertTrue(self.flushLoggedErrors(UnhandledException))

    def test_stringLiteralTooLong(self):
        """
        A string literal whose length exceeds the maximum allowed
        length results in a C{BAD} response.
        """
        self.server._literalStringLimit = 4
        self.server.lineReceived(b"001 LOGIN {5}\r\n")

        self.assertEqual(
            self.transport.value(),
            b"001 BAD Illegal syntax: Literal too long!"
            b" I accept at most 4 octets\r\n",
        )

    def test_arg_astringEmptyLine(self):
        """
        An empty string argument raises L{imap4.IllegalClientResponse}.
        """
        for empty in [b"", b"\r\n", b" "]:
            self.assertRaises(
                imap4.IllegalClientResponse, self.server.arg_astring, empty
            )

    def test_arg_astringUnmatchedQuotes(self):
        """
        An unmatched quote in a string argument raises
        L{imap4.IllegalClientResponse}.
        """
        self.assertRaises(
            imap4.IllegalClientResponse, self.server.arg_astring, b'"open'
        )

    def test_arg_astringUnmatchedLiteralBraces(self):
        """
        An unmatched brace in a string literal's size raises
        L{imap4.IllegalClientResponse}.
        """
        self.assertRaises(imap4.IllegalClientResponse, self.server.arg_astring, b"{0")

    def test_arg_astringInvalidLiteralSize(self):
        """
        A non-integral string literal size raises
        L{imap4.IllegalClientResponse}.
        """
        self.assertRaises(
            imap4.IllegalClientResponse, self.server.arg_astring, b"{[object Object]}"
        )

    def test_arg_atomEmptyLine(self):
        """
        An empty atom raises L{IllegalClientResponse}.
        """
        self.assertRaises(imap4.IllegalClientResponse, self.server.arg_atom, b"")

    def test_arg_atomMalformedAtom(self):
        """
        A malformed atom raises L{IllegalClientResponse}.
        """
        self.assertRaises(
            imap4.IllegalClientResponse, self.server.arg_atom, b" not an atom "
        )

    def test_arg_plistEmptyLine(self):
        """
        An empty parenthesized list raises L{IllegalClientResponse}.
        """
        self.assertRaises(imap4.IllegalClientResponse, self.server.arg_plist, b"")

    def test_arg_plistUnmatchedParentheses(self):
        """
        A parenthesized with unmatched parentheses raises
        L{IllegalClientResponse}.
        """
        self.assertRaises(imap4.IllegalClientResponse, self.server.arg_plist, b"(foo")
        self.assertRaises(imap4.IllegalClientResponse, self.server.arg_plist, b"foo)")

    def test_arg_literalEmptyLine(self):
        """
        An empty file literal raises L{IllegalClientResponse}.
        """
        self.assertRaises(imap4.IllegalClientResponse, self.server.arg_literal, b"")

    def test_arg_literalUnmatchedBraces(self):
        """
        A literal with unmatched braces raises
        L{IllegalClientResponse}.
        """
        self.assertRaises(imap4.IllegalClientResponse, self.server.arg_literal, b"{10")
        self.assertRaises(imap4.IllegalClientResponse, self.server.arg_literal, b"10}")

    def test_arg_literalInvalidLiteralSize(self):
        """
        A non-integral literal size raises
        L{imap4.IllegalClientResponse}.
        """
        self.assertRaises(
            imap4.IllegalClientResponse, self.server.arg_literal, b"{[object Object]}"
        )

    def test_arg_seqsetReturnsRest(self):
        """
        A sequence set returns the unparsed portion of a line.
        """
        sequence = b"1:* blah blah blah"
        _, rest = self.server.arg_seqset(sequence)
        self.assertEqual(rest, b"blah blah blah")

    def test_arg_seqsetInvalidSequence(self):
        """
        An invalid sequence raises L{imap4.IllegalClientResponse}.
        """
        self.assertRaises(imap4.IllegalClientResponse, self.server.arg_seqset, b"x:y")

    def test_arg_flaglistOneFlag(self):
        """
        A single flag that is not contained in a list is parsed.
        """
        flag = b"flag"
        parsed, rest = self.server.arg_flaglist(flag)
        self.assertEqual(parsed, [flag])
        self.assertFalse(rest)

    def test_arg_flaglistMismatchedParentehses(self):
        """
        A list of flags with unmatched parentheses raises
        L{imap4.IllegalClientResponse}.
        """
        self.assertRaises(
            imap4.IllegalClientResponse,
            self.server.arg_flaglist,
            b"(invalid",
        )

    def test_arg_flaglistMalformedFlag(self):
        """
        A list of flags that contains a malformed flag raises
        L{imap4.IllegalClientResponse}.
        """
        self.assertRaises(
            imap4.IllegalClientResponse, self.server.arg_flaglist, b"(first \x00)"
        )
        self.assertRaises(
            imap4.IllegalClientResponse, self.server.arg_flaglist, b"(first \x00second)"
        )

    def test_opt_plistMissingOpenParenthesis(self):
        """
        A line that does not begin with an open parenthesis (C{(}) is
        parsed as L{None}, and the remainder is the whole line.
        """
        line = b"not ("
        plist, remainder = self.server.opt_plist(line)
        self.assertIsNone(plist)
        self.assertEqual(remainder, line)

    def test_opt_datetimeMissingOpenQuote(self):
        """
        A line that does not begin with a double quote (C{"}) is
        parsed as L{None}, and the remainder is the whole line.
        """
        line = b'not "'
        dt, remainder = self.server.opt_datetime(line)
        self.assertIsNone(dt)
        self.assertEqual(remainder, line)

    def test_opt_datetimeMissingCloseQuote(self):
        """
        A line that does not have a closing double quote (C{"}) raises
        L{imap4.IllegalClientResponse}.
        """
        line = b'"21-Jul-2017 19:37:07 -0700'
        self.assertRaises(imap4.IllegalClientResponse, self.server.opt_datetime, line)

    def test_opt_charsetMissingIdentifier(self):
        """
        A line that contains C{CHARSET} but no character set
        identifier raises L{imap4.IllegalClientResponse}.
        """
        line = b"CHARSET"
        self.assertRaises(imap4.IllegalClientResponse, self.server.opt_charset, line)

    def test_opt_charsetEndOfLine(self):
        """
        A line that ends with a C{CHARSET} identifier is parsed as
        that identifier, and the remainder is the empty string.
        """
        line = b"CHARSET UTF-8"
        identifier, remainder = self.server.opt_charset(line)
        self.assertEqual(identifier, b"UTF-8")
        self.assertEqual(remainder, b"")

    def test_opt_charsetWithRemainder(self):
        """
        A line that has additional data after a C{CHARSET} identifier
        is parsed as that identifier, and the remainder is that
        additional data.
        """
        line = b"CHARSET UTF-8 remainder"
        identifier, remainder = self.server.opt_charset(line)
        self.assertEqual(identifier, b"UTF-8")
        self.assertEqual(remainder, b"remainder")


class IMAP4ServerSearchTests(IMAP4HelperMixin, TestCase):
    """
    Tests for the behavior of the search_* functions in L{imap4.IMAP4Server}.
    """

    def setUp(self):
        IMAP4HelperMixin.setUp(self)
        self.earlierQuery = ["10-Dec-2009"]
        self.sameDateQuery = ["13-Dec-2009"]
        self.laterQuery = ["16-Dec-2009"]
        self.seq = 0
        self.msg = FakeyMessage(
            {"date": "Mon, 13 Dec 2009 21:25:10 GMT"},
            [],
            "13 Dec 2009 00:00:00 GMT",
            "",
            1234,
            None,
        )

    def test_searchSentBefore(self):
        """
        L{imap4.IMAP4Server.search_SENTBEFORE} returns True if the message date
        is earlier than the query date.
        """
        self.assertFalse(
            self.server.search_SENTBEFORE(self.earlierQuery, self.seq, self.msg)
        )
        self.assertTrue(
            self.server.search_SENTBEFORE(self.laterQuery, self.seq, self.msg)
        )

    def test_searchWildcard(self):
        """
        L{imap4.IMAP4Server.search_UID} returns True if the message UID is in
        the search range.
        """
        self.assertFalse(
            self.server.search_UID([b"2:3"], self.seq, self.msg, (1, 1234))
        )
        # 2:* should get translated to 2:<max UID> and then to 1:2
        self.assertTrue(self.server.search_UID([b"2:*"], self.seq, self.msg, (1, 1234)))
        self.assertTrue(self.server.search_UID([b"*"], self.seq, self.msg, (1, 1234)))

    def test_searchWildcardHigh(self):
        """
        L{imap4.IMAP4Server.search_UID} should return True if there is a
        wildcard, because a wildcard means "highest UID in the mailbox".
        """
        self.assertTrue(
            self.server.search_UID([b"1235:*"], self.seq, self.msg, (1234, 1))
        )

    def test_reversedSearchTerms(self):
        """
        L{imap4.IMAP4Server.search_SENTON} returns True if the message date is
        the same as the query date.
        """
        msgset = imap4.parseIdList(b"4:2")
        self.assertEqual(list(msgset), [2, 3, 4])

    def test_searchSentOn(self):
        """
        L{imap4.IMAP4Server.search_SENTON} returns True if the message date is
        the same as the query date.
        """
        self.assertFalse(
            self.server.search_SENTON(self.earlierQuery, self.seq, self.msg)
        )
        self.assertTrue(
            self.server.search_SENTON(self.sameDateQuery, self.seq, self.msg)
        )
        self.assertFalse(self.server.search_SENTON(self.laterQuery, self.seq, self.msg))

    def test_searchSentSince(self):
        """
        L{imap4.IMAP4Server.search_SENTSINCE} returns True if the message date
        is later than the query date.
        """
        self.assertTrue(
            self.server.search_SENTSINCE(self.earlierQuery, self.seq, self.msg)
        )
        self.assertFalse(
            self.server.search_SENTSINCE(self.laterQuery, self.seq, self.msg)
        )

    def test_searchOr(self):
        """
        L{imap4.IMAP4Server.search_OR} returns true if either of the two
        expressions supplied to it returns true and returns false if neither
        does.
        """
        self.assertTrue(
            self.server.search_OR(
                ["SENTSINCE"] + self.earlierQuery + ["SENTSINCE"] + self.laterQuery,
                self.seq,
                self.msg,
                (None, None),
            )
        )
        self.assertTrue(
            self.server.search_OR(
                ["SENTSINCE"] + self.laterQuery + ["SENTSINCE"] + self.earlierQuery,
                self.seq,
                self.msg,
                (None, None),
            )
        )
        self.assertFalse(
            self.server.search_OR(
                ["SENTON"] + self.laterQuery + ["SENTSINCE"] + self.laterQuery,
                self.seq,
                self.msg,
                (None, None),
            )
        )

    def test_searchNot(self):
        """
        L{imap4.IMAP4Server.search_NOT} returns the negation of the result
        of the expression supplied to it.
        """
        self.assertFalse(
            self.server.search_NOT(
                ["SENTSINCE"] + self.earlierQuery, self.seq, self.msg, (None, None)
            )
        )
        self.assertTrue(
            self.server.search_NOT(
                ["SENTON"] + self.laterQuery, self.seq, self.msg, (None, None)
            )
        )

    def test_searchBefore(self):
        """
        L{imap4.IMAP4Server.search_BEFORE} returns True if the
        internal message date is before the query date.
        """
        self.assertFalse(
            self.server.search_BEFORE(self.earlierQuery, self.seq, self.msg)
        )
        self.assertFalse(
            self.server.search_BEFORE(self.sameDateQuery, self.seq, self.msg)
        )
        self.assertTrue(self.server.search_BEFORE(self.laterQuery, self.seq, self.msg))

    def test_searchOn(self):
        """
        L{imap4.IMAP4Server.search_ON} returns True if the
        internal message date is the same as the query date.
        """
        self.assertFalse(self.server.search_ON(self.earlierQuery, self.seq, self.msg))
        self.assertFalse(self.server.search_ON(self.sameDateQuery, self.seq, self.msg))
        self.assertFalse(self.server.search_ON(self.laterQuery, self.seq, self.msg))

    def test_searchSince(self):
        """
        L{imap4.IMAP4Server.search_SINCE} returns True if the
        internal message date is greater than the query date.
        """
        self.assertTrue(self.server.search_SINCE(self.earlierQuery, self.seq, self.msg))
        self.assertTrue(
            self.server.search_SINCE(self.sameDateQuery, self.seq, self.msg)
        )
        self.assertFalse(self.server.search_SINCE(self.laterQuery, self.seq, self.msg))


@implementer(IRealm)
class TestRealm:
    """
    A L{IRealm} for tests.

    @cvar theAccount: An C{Account} instance.  Tests can set this to
        ensure predictable account retrieval.
    """

    theAccount = None

    def __init__(self, accountHolder=None):
        """
        Create a realm for testing.

        @param accountHolder: (optional) An object whose C{theAccount}
            attribute will be returned instead of
            L{TestRealm.theAccount}.  Attribute access occurs on every
            avatar request, so any modifications to
            C{accountHolder.theAccount} will be reflected here.
        """
        if accountHolder:
            self._getAccount = lambda: accountHolder.theAccount
        else:
            self._getAccount = lambda: self.theAccount

    def requestAvatar(self, avatarId, mind, *interfaces):
        return imap4.IAccount, self._getAccount(), lambda: None


class TestChecker:
    credentialInterfaces = (IUsernameHashedPassword, IUsernamePassword)

    users = {b"testuser": b"secret"}

    def requestAvatarId(self, credentials):
        if credentials.username in self.users:
            return defer.maybeDeferred(
                credentials.checkPassword, self.users[credentials.username]
            ).addCallback(self._cbCheck, credentials.username)

    def _cbCheck(self, result, username):
        if result:
            return username
        raise UnauthorizedLogin()


class AuthenticatorTests(IMAP4HelperMixin, TestCase):
    def setUp(self):
        IMAP4HelperMixin.setUp(self)

        realm = TestRealm()
        realm.theAccount = Account(b"testuser")
        self.portal = Portal(realm)
        self.portal.registerChecker(TestChecker())
        self.server.portal = self.portal

        self.authenticated = 0
        self.account = realm.theAccount

    def test_customChallengers(self):
        """
        L{imap4.IMAP4Server} accepts a L{dict} mapping challenge type
        names to L{twisted.mail.interfaces.IChallengeResponse}
        providers.
        """

        @implementer(IChallengeResponse, IUsernamePassword)
        class SPECIALAuth:
            def getChallenge(self):
                return b"SPECIAL"

            def setResponse(self, response):
                self.username, self.password = response.split(None, 1)

            def moreChallenges(self):
                return False

            def checkPassword(self, password):
                self.password = self.password

        special = SPECIALAuth()
        verifyObject(IChallengeResponse, special)

        server = imap4.IMAP4Server({b"SPECIAL": SPECIALAuth})
        server.portal = self.portal

        transport = StringTransport()
        server.makeConnection(transport)
        self.addCleanup(server.connectionLost, error.ConnectionDone("Connection done."))

        self.assertIn(b"AUTH=SPECIAL", transport.value())

        transport.clear()
        server.dataReceived(b"001 AUTHENTICATE SPECIAL\r\n")

        self.assertIn(base64.b64encode(special.getChallenge()), transport.value())

        transport.clear()
        server.dataReceived(base64.b64encode(b"username password") + b"\r\n")

        self.assertEqual(transport.value(), b"001 OK Authentication successful\r\n")

    def test_unsupportedMethod(self):
        """
        An unsupported C{AUTHENTICATE} method results in a negative
        response.
        """
        server = imap4.IMAP4Server()
        server.portal = self.portal

        transport = StringTransport()
        server.makeConnection(transport)
        self.addCleanup(server.connectionLost, error.ConnectionDone("Connection done."))

        transport.clear()

        server.dataReceived(b"001 AUTHENTICATE UNKNOWN\r\n")
        self.assertEqual(
            transport.value(), b"001 NO AUTHENTICATE method unsupported\r\n"
        )

    def test_missingPortal(self):
        """
        An L{imap4.IMAP4Server} that is missing a L{Portal} responds
        negatively to an authentication
        """
        self.server.challengers[b"LOGIN"] = imap4.LOGINCredentials

        cAuth = imap4.LOGINAuthenticator(b"testuser")
        self.client.registerAuthenticator(cAuth)

        self.server.portal = None

        def auth():
            return self.client.authenticate(b"secret")

        d = self.connected.addCallback(strip(auth))
        d.addErrback(
            self.assertClientFailureMessage, b"Temporary authentication failure"
        )
        d.addCallbacks(self._cbStopClient, self._ebGeneral)

        return defer.gatherResults([d, self.loopback()])

    def test_challengerRaisesException(self):
        """
        When a challenger's
        L{getChallenge<IChallengeResponse.getChallenge>} method raises
        any exception, a C{NO} response is sent.
        """

        @implementer(IChallengeResponse)
        class ValueErrorAuthChallenge:
            message = b"A challenge failure"

            def getChallenge(self):
                raise ValueError(self.message)

            def setResponse(self, response):
                """
                Never called.

                @param response: See L{IChallengeResponse.setResponse}
                """

            def moreChallenges(self):
                """
                Never called.
                """

        @implementer(IClientAuthentication)
        class ValueErrorAuthenticator:
            def getName(self):
                return b"ERROR"

            def challengeResponse(self, secret, chal):
                return b"IGNORED"

        bad = ValueErrorAuthChallenge()
        verifyObject(IChallengeResponse, bad)

        self.server.challengers[b"ERROR"] = ValueErrorAuthChallenge
        self.client.registerAuthenticator(ValueErrorAuthenticator())

        def auth():
            return self.client.authenticate(b"secret")

        d = self.connected.addCallback(strip(auth))
        d.addErrback(
            self.assertClientFailureMessage,
            ("Server error: " + str(ValueErrorAuthChallenge.message)).encode("ascii"),
        )
        d.addCallbacks(self._cbStopClient, self._ebGeneral)

        return defer.gatherResults([d, self.loopback()])

    def test_authNotBase64(self):
        """
        A client that responds with a challenge that cannot be decoded
        as Base 64 receives an L{IllegalClientResponse}.
        """

        @implementer(IChallengeResponse)
        class NotBase64AuthChallenge:
            message = b"Malformed Response - not base64"

            def getChallenge(self):
                return b"SomeChallenge"

            def setResponse(self, response):
                """
                Never called.

                @param response: See L{IChallengeResponse.setResponse}
                """

            def moreChallenges(self):
                """
                Never called.
                """

        notBase64 = NotBase64AuthChallenge()
        verifyObject(IChallengeResponse, notBase64)

        server = imap4.IMAP4Server()
        server.portal = self.portal
        server.challengers[b"NOTBASE64"] = NotBase64AuthChallenge

        transport = StringTransport()
        server.makeConnection(transport)
        self.addCleanup(server.connectionLost, error.ConnectionDone("Connection done."))

        self.assertIn(b"AUTH=NOTBASE64", transport.value())

        transport.clear()
        server.dataReceived(b"001 AUTHENTICATE NOTBASE64\r\n")

        self.assertIn(base64.b64encode(notBase64.getChallenge()), transport.value())

        transport.clear()
        server.dataReceived(b"\x00 Not base64\r\n")

        self.assertEqual(
            transport.value(),
            b"".join([b"001 NO Authentication failed: ", notBase64.message, b"\r\n"]),
        )

    def test_unhandledCredentials(self):
        """
        A challenger that causes the login to fail
        L{UnhandledCredentials} results in an C{NO} response.

        @return: A L{Deferred} that fires when the authorization has
            failed.
        """
        realm = TestRealm()
        portal = Portal(realm)
        # This portal has no checkers, so all logins will fail with
        # UnhandledCredentials
        self.server.portal = portal

        self.server.challengers[b"LOGIN"] = loginCred = imap4.LOGINCredentials

        verifyClass(IChallengeResponse, loginCred)

        cAuth = imap4.LOGINAuthenticator(b"testuser")
        self.client.registerAuthenticator(cAuth)

        def auth():
            return self.client.authenticate(b"secret")

        d1 = self.connected.addCallback(strip(auth))
        d1.addErrback(
            self.assertClientFailureMessage,
            b"Authentication failed: server misconfigured",
        )
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d

    def test_unexpectedLoginFailure(self):
        """
        If the portal raises an exception other than
        L{UnauthorizedLogin} or L{UnhandledCredentials}, the server
        responds with a C{BAD} response and the exception is logged.
        """

        class UnexpectedException(Exception):
            """
            An unexpected exception.
            """

        class FailingChecker:
            """
            A credentials checker whose L{requestAvatarId} method
            raises L{UnexpectedException}.
            """

            credentialInterfaces = (IUsernameHashedPassword, IUsernamePassword)

            def requestAvatarId(self, credentials):
                raise UnexpectedException("Unexpected error.")

        realm = TestRealm()
        portal = Portal(realm)
        portal.registerChecker(FailingChecker())
        self.server.portal = portal

        self.server.challengers[b"LOGIN"] = loginCred = imap4.LOGINCredentials

        verifyClass(IChallengeResponse, loginCred)

        cAuth = imap4.LOGINAuthenticator(b"testuser")
        self.client.registerAuthenticator(cAuth)

        def auth():
            return self.client.authenticate(b"secret")

        def assertUnexpectedExceptionLogged():
            self.assertTrue(self.flushLoggedErrors(UnexpectedException))

        d1 = self.connected.addCallback(strip(auth))
        d1.addErrback(
            self.assertClientFailureMessage, b"Server error: login failed unexpectedly"
        )
        d1.addCallback(strip(assertUnexpectedExceptionLogged))
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d

    def testCramMD5(self):
        self.server.challengers[b"CRAM-MD5"] = CramMD5Credentials
        cAuth = imap4.CramMD5ClientAuthenticator(b"testuser")
        self.client.registerAuthenticator(cAuth)

        def auth():
            return self.client.authenticate(b"secret")

        def authed():
            self.authenticated = 1

        d1 = self.connected.addCallback(strip(auth))
        d1.addCallbacks(strip(authed), self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d2 = self.loopback()
        d = defer.gatherResults([d1, d2])
        return d.addCallback(self._cbTestCramMD5)

    def _cbTestCramMD5(self, ignored):
        self.assertEqual(self.authenticated, 1)
        self.assertEqual(self.server.account, self.account)

    def testFailedCramMD5(self):
        self.server.challengers[b"CRAM-MD5"] = CramMD5Credentials
        cAuth = imap4.CramMD5ClientAuthenticator(b"testuser")
        self.client.registerAuthenticator(cAuth)

        def misauth():
            return self.client.authenticate(b"not the secret")

        def authed():
            self.authenticated = 1

        def misauthed():
            self.authenticated = -1

        d1 = self.connected.addCallback(strip(misauth))
        d1.addCallbacks(strip(authed), strip(misauthed))
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d.addCallback(self._cbTestFailedCramMD5)

    def _cbTestFailedCramMD5(self, ignored):
        self.assertEqual(self.authenticated, -1)
        self.assertEqual(self.server.account, None)

    def testLOGIN(self):
        self.server.challengers[b"LOGIN"] = loginCred = imap4.LOGINCredentials

        verifyClass(IChallengeResponse, loginCred)

        cAuth = imap4.LOGINAuthenticator(b"testuser")
        self.client.registerAuthenticator(cAuth)

        def auth():
            return self.client.authenticate(b"secret")

        def authed():
            self.authenticated = 1

        d1 = self.connected.addCallback(strip(auth))
        d1.addCallbacks(strip(authed), self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d.addCallback(self._cbTestLOGIN)

    def _cbTestLOGIN(self, ignored):
        self.assertEqual(self.authenticated, 1)
        self.assertEqual(self.server.account, self.account)

    def testFailedLOGIN(self):
        self.server.challengers[b"LOGIN"] = imap4.LOGINCredentials
        cAuth = imap4.LOGINAuthenticator(b"testuser")
        self.client.registerAuthenticator(cAuth)

        def misauth():
            return self.client.authenticate(b"not the secret")

        def authed():
            self.authenticated = 1

        def misauthed():
            self.authenticated = -1

        d1 = self.connected.addCallback(strip(misauth))
        d1.addCallbacks(strip(authed), strip(misauthed))
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d.addCallback(self._cbTestFailedLOGIN)

    def _cbTestFailedLOGIN(self, ignored):
        self.assertEqual(self.authenticated, -1)
        self.assertEqual(self.server.account, None)

    def testPLAIN(self):
        self.server.challengers[b"PLAIN"] = plainCred = imap4.PLAINCredentials

        verifyClass(IChallengeResponse, plainCred)

        cAuth = imap4.PLAINAuthenticator(b"testuser")
        self.client.registerAuthenticator(cAuth)

        def auth():
            return self.client.authenticate(b"secret")

        def authed():
            self.authenticated = 1

        d1 = self.connected.addCallback(strip(auth))
        d1.addCallbacks(strip(authed), self._ebGeneral)
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d.addCallback(self._cbTestPLAIN)

    def _cbTestPLAIN(self, ignored):
        self.assertEqual(self.authenticated, 1)
        self.assertEqual(self.server.account, self.account)

    def testFailedPLAIN(self):
        self.server.challengers[b"PLAIN"] = imap4.PLAINCredentials
        cAuth = imap4.PLAINAuthenticator(b"testuser")
        self.client.registerAuthenticator(cAuth)

        def misauth():
            return self.client.authenticate(b"not the secret")

        def authed():
            self.authenticated = 1

        def misauthed():
            self.authenticated = -1

        d1 = self.connected.addCallback(strip(misauth))
        d1.addCallbacks(strip(authed), strip(misauthed))
        d1.addCallbacks(self._cbStopClient, self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d.addCallback(self._cbTestFailedPLAIN)

    def _cbTestFailedPLAIN(self, ignored):
        self.assertEqual(self.authenticated, -1)
        self.assertEqual(self.server.account, None)


class SASLPLAINTests(TestCase):
    """
    Tests for I{SASL PLAIN} authentication, as implemented by
    L{imap4.PLAINAuthenticator} and L{imap4.PLAINCredentials}.

    @see: U{http://www.faqs.org/rfcs/rfc2595.html}
    @see: U{http://www.faqs.org/rfcs/rfc4616.html}
    """

    def test_authenticatorChallengeResponse(self):
        """
        L{PLAINAuthenticator.challengeResponse} returns challenge strings of
        the form::

            NUL<authn-id>NUL<secret>
        """
        username = b"testuser"
        secret = b"secret"
        chal = b"challenge"
        cAuth = imap4.PLAINAuthenticator(username)
        response = cAuth.challengeResponse(secret, chal)
        self.assertEqual(response, b"\0" + username + b"\0" + secret)

    def test_credentialsSetResponse(self):
        """
        L{PLAINCredentials.setResponse} parses challenge strings of the
        form::

            NUL<authn-id>NUL<secret>
        """
        cred = imap4.PLAINCredentials()
        cred.setResponse(b"\0testuser\0secret")
        self.assertEqual(cred.username, b"testuser")
        self.assertEqual(cred.password, b"secret")

    def test_credentialsInvalidResponse(self):
        """
        L{PLAINCredentials.setResponse} raises L{imap4.IllegalClientResponse}
        when passed a string not of the expected form.
        """
        cred = imap4.PLAINCredentials()
        self.assertRaises(imap4.IllegalClientResponse, cred.setResponse, b"hello")
        self.assertRaises(
            imap4.IllegalClientResponse, cred.setResponse, b"hello\0world"
        )
        self.assertRaises(
            imap4.IllegalClientResponse, cred.setResponse, b"hello\0world\0Zoom!\0"
        )


class UnsolicitedResponseTests(IMAP4HelperMixin, TestCase):
    def testReadWrite(self):
        def login():
            return self.client.login(b"testuser", b"password-test")

        def loggedIn():
            self.server.modeChanged(1)

        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(loggedIn)).addErrback(self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d.addCallback(self._cbTestReadWrite)

    def _cbTestReadWrite(self, ignored):
        E = self.client.events
        self.assertEqual(E, [["modeChanged", 1]])

    def testReadOnly(self):
        def login():
            return self.client.login(b"testuser", b"password-test")

        def loggedIn():
            self.server.modeChanged(0)

        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(loggedIn)).addErrback(self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d.addCallback(self._cbTestReadOnly)

    def _cbTestReadOnly(self, ignored):
        E = self.client.events
        self.assertEqual(E, [["modeChanged", 0]])

    def testFlagChange(self):
        flags = {1: ["\\Answered", "\\Deleted"], 5: [], 10: ["\\Recent"]}

        def login():
            return self.client.login(b"testuser", b"password-test")

        def loggedIn():
            self.server.flagsChanged(flags)

        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(loggedIn)).addErrback(self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d.addCallback(self._cbTestFlagChange, flags)

    def _cbTestFlagChange(self, ignored, flags):
        E = self.client.events
        expect = [["flagsChanged", {x[0]: x[1]}] for x in flags.items()]
        E.sort(key=lambda o: o[0])
        expect.sort(key=lambda o: o[0])
        self.assertEqual(E, expect)

    def testNewMessages(self):
        def login():
            return self.client.login(b"testuser", b"password-test")

        def loggedIn():
            self.server.newMessages(10, None)

        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(loggedIn)).addErrback(self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d.addCallback(self._cbTestNewMessages)

    def _cbTestNewMessages(self, ignored):
        E = self.client.events
        self.assertEqual(E, [["newMessages", 10, None]])

    def testNewRecentMessages(self):
        def login():
            return self.client.login(b"testuser", b"password-test")

        def loggedIn():
            self.server.newMessages(None, 10)

        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(loggedIn)).addErrback(self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d.addCallback(self._cbTestNewRecentMessages)

    def _cbTestNewRecentMessages(self, ignored):
        E = self.client.events
        self.assertEqual(E, [["newMessages", None, 10]])

    def testNewMessagesAndRecent(self):
        def login():
            return self.client.login(b"testuser", b"password-test")

        def loggedIn():
            self.server.newMessages(20, 10)

        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(loggedIn)).addErrback(self._ebGeneral)
        d = defer.gatherResults([self.loopback(), d1])
        return d.addCallback(self._cbTestNewMessagesAndRecent)

    def _cbTestNewMessagesAndRecent(self, ignored):
        E = self.client.events
        self.assertEqual(E, [["newMessages", 20, None], ["newMessages", None, 10]])


class ClientCapabilityTests(TestCase):
    """
    Tests for issuance of the CAPABILITY command and handling of its response.
    """

    def setUp(self):
        """
        Create an L{imap4.IMAP4Client} connected to a L{StringTransport}.
        """
        self.transport = StringTransport()
        self.protocol = imap4.IMAP4Client()
        self.protocol.makeConnection(self.transport)
        self.protocol.dataReceived(b"* OK [IMAP4rev1]\r\n")

    def test_simpleAtoms(self):
        """
        A capability response consisting only of atoms without C{'='} in them
        should result in a dict mapping those atoms to L{None}.
        """
        capabilitiesResult = self.protocol.getCapabilities(useCache=False)
        self.protocol.dataReceived(b"* CAPABILITY IMAP4rev1 LOGINDISABLED\r\n")
        self.protocol.dataReceived(b"0001 OK Capability completed.\r\n")

        def gotCapabilities(capabilities):
            self.assertEqual(capabilities, {b"IMAP4rev1": None, b"LOGINDISABLED": None})

        capabilitiesResult.addCallback(gotCapabilities)
        return capabilitiesResult

    def test_categoryAtoms(self):
        """
        A capability response consisting of atoms including C{'='} should have
        those atoms split on that byte and have capabilities in the same
        category aggregated into lists in the resulting dictionary.

        (n.b. - I made up the word "category atom"; the protocol has no notion
        of structure here, but rather allows each capability to define the
        semantics of its entry in the capability response in a freeform manner.
        If I had realized this earlier, the API for capabilities would look
        different.  As it is, we can hope that no one defines any crazy
        semantics which are incompatible with this API, or try to figure out a
        better API when someone does. -exarkun)
        """
        capabilitiesResult = self.protocol.getCapabilities(useCache=False)
        self.protocol.dataReceived(b"* CAPABILITY IMAP4rev1 AUTH=LOGIN AUTH=PLAIN\r\n")
        self.protocol.dataReceived(b"0001 OK Capability completed.\r\n")

        def gotCapabilities(capabilities):
            self.assertEqual(
                capabilities, {b"IMAP4rev1": None, b"AUTH": [b"LOGIN", b"PLAIN"]}
            )

        capabilitiesResult.addCallback(gotCapabilities)
        return capabilitiesResult

    def test_mixedAtoms(self):
        """
        A capability response consisting of both simple and category atoms of
        the same type should result in a list containing L{None} as well as the
        values for the category.
        """
        capabilitiesResult = self.protocol.getCapabilities(useCache=False)
        # Exercise codepath for both orderings of =-having and =-missing
        # capabilities.
        self.protocol.dataReceived(
            b"* CAPABILITY IMAP4rev1 FOO FOO=BAR BAR=FOO BAR\r\n"
        )
        self.protocol.dataReceived(b"0001 OK Capability completed.\r\n")

        def gotCapabilities(capabilities):
            self.assertEqual(
                capabilities,
                {b"IMAP4rev1": None, b"FOO": [None, b"BAR"], b"BAR": [b"FOO", None]},
            )

        capabilitiesResult.addCallback(gotCapabilities)
        return capabilitiesResult


class StillSimplerClient(imap4.IMAP4Client):
    """
    An IMAP4 client which keeps track of unsolicited flag changes.
    """

    def __init__(self):
        imap4.IMAP4Client.__init__(self)
        self.flags = {}

    def flagsChanged(self, newFlags):
        self.flags.update(newFlags)


class HandCraftedTests(IMAP4HelperMixin, TestCase):
    def testTrailingLiteral(self):
        transport = StringTransport()
        c = imap4.IMAP4Client()
        c.makeConnection(transport)
        c.lineReceived(b"* OK [IMAP4rev1]")

        def cbCheckTransport(ignored):
            self.assertEqual(
                transport.value().splitlines()[-1],
                b"0003 FETCH 1 (RFC822)",
            )

        def cbSelect(ignored):
            d = c.fetchMessage("1")
            c.dataReceived(
                b"* 1 FETCH (RFC822 {10}\r\n0123456789\r\n RFC822.SIZE 10)\r\n"
            )
            c.dataReceived(b"0003 OK FETCH\r\n")
            d.addCallback(cbCheckTransport)
            return d

        def cbLogin(ignored):
            d = c.select("inbox")
            c.lineReceived(b"0002 OK SELECT")
            d.addCallback(cbSelect)
            return d

        d = c.login(b"blah", b"blah")
        c.dataReceived(b"0001 OK LOGIN\r\n")
        d.addCallback(cbLogin)
        return d

    def test_fragmentedStringLiterals(self):
        """
        String literals whose data is not immediately available are
        parsed.
        """
        self.server.checker.addUser(b"testuser", b"password-test")
        transport = StringTransport()
        self.server.makeConnection(transport)

        transport.clear()
        self.server.dataReceived(b"01 LOGIN {8}\r\n")
        self.assertEqual(transport.value(), b"+ Ready for 8 octets of text\r\n")

        transport.clear()
        self.server.dataReceived(b"testuser {13}\r\n")
        self.assertEqual(transport.value(), b"+ Ready for 13 octets of text\r\n")

        transport.clear()
        self.server.dataReceived(b"password")
        self.assertNot(transport.value())
        self.server.dataReceived(b"-test\r\n")
        self.assertEqual(transport.value(), b"01 OK LOGIN succeeded\r\n")
        self.assertEqual(self.server.state, "auth")

        self.server.connectionLost(error.ConnectionDone("Connection done."))

    def test_emptyStringLiteral(self):
        """
        Empty string literals are parsed.
        """
        self.server.checker.users = {b"": b""}
        transport = StringTransport()
        self.server.makeConnection(transport)

        transport.clear()
        self.server.dataReceived(b"01 LOGIN {0}\r\n")
        self.assertEqual(transport.value(), b"+ Ready for 0 octets of text\r\n")

        transport.clear()
        self.server.dataReceived(b"{0}\r\n")
        self.assertEqual(transport.value(), b"01 OK LOGIN succeeded\r\n")
        self.assertEqual(self.server.state, "auth")

        self.server.connectionLost(error.ConnectionDone("Connection done."))

    def test_unsolicitedResponseMixedWithSolicitedResponse(self):
        """
        If unsolicited data is received along with solicited data in the
        response to a I{FETCH} command issued by L{IMAP4Client.fetchSpecific},
        the unsolicited data is passed to the appropriate callback and not
        included in the result with which the L{Deferred} returned by
        L{IMAP4Client.fetchSpecific} fires.
        """
        transport = StringTransport()
        c = StillSimplerClient()
        c.makeConnection(transport)
        c.lineReceived(b"* OK [IMAP4rev1]")

        def login():
            d = c.login(b"blah", b"blah")
            c.dataReceived(b"0001 OK LOGIN\r\n")
            return d

        def select():
            d = c.select("inbox")
            c.lineReceived(b"0002 OK SELECT")
            return d

        def fetch():
            d = c.fetchSpecific(
                "1:*", headerType="HEADER.FIELDS", headerArgs=["SUBJECT"]
            )
            c.dataReceived(b'* 1 FETCH (BODY[HEADER.FIELDS ("SUBJECT")] {38}\r\n')
            c.dataReceived(b"Subject: Suprise for your woman...\r\n")
            c.dataReceived(b"\r\n")
            c.dataReceived(b")\r\n")
            c.dataReceived(b"* 1 FETCH (FLAGS (\\Seen))\r\n")
            c.dataReceived(b'* 2 FETCH (BODY[HEADER.FIELDS ("SUBJECT")] {75}\r\n')
            c.dataReceived(
                b"Subject: What you been doing. Order your meds here . ,. handcuff madsen\r\n"
            )
            c.dataReceived(b"\r\n")
            c.dataReceived(b")\r\n")
            c.dataReceived(b"0003 OK FETCH completed\r\n")
            return d

        def test(res):
            self.assertEqual(
                transport.value().splitlines()[-1],
                b"0003 FETCH 1:* BODY[HEADER.FIELDS (SUBJECT)]",
            )

            self.assertEqual(
                res,
                {
                    1: [
                        [
                            "BODY",
                            ["HEADER.FIELDS", ["SUBJECT"]],
                            "Subject: Suprise for your woman...\r\n\r\n",
                        ]
                    ],
                    2: [
                        [
                            "BODY",
                            ["HEADER.FIELDS", ["SUBJECT"]],
                            "Subject: What you been doing. Order your meds here . ,. handcuff madsen\r\n\r\n",
                        ]
                    ],
                },
            )

            self.assertEqual(c.flags, {1: ["\\Seen"]})

        return (
            login()
            .addCallback(strip(select))
            .addCallback(strip(fetch))
            .addCallback(test)
        )

    def test_literalWithoutPrecedingWhitespace(self):
        """
        Literals should be recognized even when they are not preceded by
        whitespace.
        """
        transport = StringTransport()
        protocol = imap4.IMAP4Client()

        protocol.makeConnection(transport)
        protocol.lineReceived(b"* OK [IMAP4rev1]")

        def login():
            d = protocol.login(b"blah", b"blah")
            protocol.dataReceived(b"0001 OK LOGIN\r\n")
            return d

        def select():
            d = protocol.select(b"inbox")
            protocol.lineReceived(b"0002 OK SELECT")
            return d

        def fetch():
            d = protocol.fetchSpecific(
                "1:*", headerType="HEADER.FIELDS", headerArgs=["SUBJECT"]
            )
            protocol.dataReceived(
                b'* 1 FETCH (BODY[HEADER.FIELDS ({7}\r\nSUBJECT)] "Hello")\r\n'
            )
            protocol.dataReceived(b"0003 OK FETCH completed\r\n")
            return d

        def test(result):
            self.assertEqual(
                transport.value().splitlines()[-1],
                b"0003 FETCH 1:* BODY[HEADER.FIELDS (SUBJECT)]",
            )
            self.assertEqual(
                result, {1: [["BODY", ["HEADER.FIELDS", ["SUBJECT"]], "Hello"]]}
            )

        d = login()
        d.addCallback(strip(select))
        d.addCallback(strip(fetch))
        d.addCallback(test)
        return d

    def test_nonIntegerLiteralLength(self):
        """
        If the server sends a literal length which cannot be parsed as an
        integer, L{IMAP4Client.lineReceived} should cause the protocol to be
        disconnected by raising L{imap4.IllegalServerResponse}.
        """
        transport = StringTransport()
        protocol = imap4.IMAP4Client()

        protocol.makeConnection(transport)
        protocol.lineReceived(b"* OK [IMAP4rev1]")

        def login():
            d = protocol.login(b"blah", b"blah")
            protocol.dataReceived(b"0001 OK LOGIN\r\n")
            return d

        def select():
            d = protocol.select("inbox")
            protocol.lineReceived(b"0002 OK SELECT")
            return d

        def fetch():
            protocol.fetchSpecific(
                "1:*", headerType="HEADER.FIELDS", headerArgs=["SUBJECT"]
            )

            self.assertEqual(
                transport.value().splitlines()[-1],
                b"0003 FETCH 1:* BODY[HEADER.FIELDS (SUBJECT)]",
            )

            self.assertRaises(
                imap4.IllegalServerResponse,
                protocol.dataReceived,
                b"* 1 FETCH {xyz}\r\n...",
            )

        d = login()
        d.addCallback(strip(select))
        d.addCallback(strip(fetch))
        return d

    def test_flagsChangedInsideFetchSpecificResponse(self):
        """
        Any unrequested flag information received along with other requested
        information in an untagged I{FETCH} received in response to a request
        issued with L{IMAP4Client.fetchSpecific} is passed to the
        C{flagsChanged} callback.
        """
        transport = StringTransport()
        c = StillSimplerClient()
        c.makeConnection(transport)
        c.lineReceived(b"* OK [IMAP4rev1]")

        def login():
            d = c.login(b"blah", b"blah")
            c.dataReceived(b"0001 OK LOGIN\r\n")
            return d

        def select():
            d = c.select("inbox")
            c.lineReceived(b"0002 OK SELECT")
            return d

        def fetch():
            d = c.fetchSpecific(
                b"1:*", headerType="HEADER.FIELDS", headerArgs=["SUBJECT"]
            )
            # This response includes FLAGS after the requested data.
            c.dataReceived(b'* 1 FETCH (BODY[HEADER.FIELDS ("SUBJECT")] {22}\r\n')
            c.dataReceived(b"Subject: subject one\r\n")
            c.dataReceived(b" FLAGS (\\Recent))\r\n")
            # And this one includes it before!  Either is possible.
            c.dataReceived(
                b'* 2 FETCH (FLAGS (\\Seen) BODY[HEADER.FIELDS ("SUBJECT")] {22}\r\n'
            )
            c.dataReceived(b"Subject: subject two\r\n")
            c.dataReceived(b")\r\n")
            c.dataReceived(b"0003 OK FETCH completed\r\n")
            return d

        def test(res):
            self.assertEqual(
                res,
                {
                    1: [
                        [
                            "BODY",
                            ["HEADER.FIELDS", ["SUBJECT"]],
                            "Subject: subject one\r\n",
                        ]
                    ],
                    2: [
                        [
                            "BODY",
                            ["HEADER.FIELDS", ["SUBJECT"]],
                            "Subject: subject two\r\n",
                        ]
                    ],
                },
            )

            self.assertEqual(c.flags, {1: ["\\Recent"], 2: ["\\Seen"]})

        return (
            login()
            .addCallback(strip(select))
            .addCallback(strip(fetch))
            .addCallback(test)
        )

    def test_flagsChangedInsideFetchMessageResponse(self):
        """
        Any unrequested flag information received along with other requested
        information in an untagged I{FETCH} received in response to a request
        issued with L{IMAP4Client.fetchMessage} is passed to the
        C{flagsChanged} callback.
        """
        transport = StringTransport()
        c = StillSimplerClient()
        c.makeConnection(transport)
        c.lineReceived(b"* OK [IMAP4rev1]")

        def login():
            d = c.login(b"blah", b"blah")
            c.dataReceived(b"0001 OK LOGIN\r\n")
            return d

        def select():
            d = c.select("inbox")
            c.lineReceived(b"0002 OK SELECT")
            return d

        def fetch():
            d = c.fetchMessage("1:*")
            c.dataReceived(b"* 1 FETCH (RFC822 {24}\r\n")
            c.dataReceived(b"Subject: first subject\r\n")
            c.dataReceived(b" FLAGS (\\Seen))\r\n")
            c.dataReceived(b"* 2 FETCH (FLAGS (\\Recent \\Seen) RFC822 {25}\r\n")
            c.dataReceived(b"Subject: second subject\r\n")
            c.dataReceived(b")\r\n")
            c.dataReceived(b"0003 OK FETCH completed\r\n")
            return d

        def test(res):
            self.assertEqual(
                transport.value().splitlines()[-1],
                b"0003 FETCH 1:* (RFC822)",
            )

            self.assertEqual(
                res,
                {
                    1: {"RFC822": "Subject: first subject\r\n"},
                    2: {"RFC822": "Subject: second subject\r\n"},
                },
            )

            self.assertEqual(c.flags, {1: ["\\Seen"], 2: ["\\Recent", "\\Seen"]})

        return (
            login()
            .addCallback(strip(select))
            .addCallback(strip(fetch))
            .addCallback(test)
        )

    def test_authenticationChallengeDecodingException(self):
        """
        When decoding a base64 encoded authentication message from the server,
        decoding errors are logged and then the client closes the connection.
        """
        transport = StringTransportWithDisconnection()
        protocol = imap4.IMAP4Client()
        transport.protocol = protocol

        protocol.makeConnection(transport)
        protocol.lineReceived(
            b"* OK [CAPABILITY IMAP4rev1 IDLE NAMESPACE AUTH=CRAM-MD5] "
            b"Twisted IMAP4rev1 Ready"
        )
        cAuth = imap4.CramMD5ClientAuthenticator(b"testuser")
        protocol.registerAuthenticator(cAuth)

        d = protocol.authenticate("secret")
        # Should really be something describing the base64 decode error.  See
        # #6021.
        self.assertFailure(d, error.ConnectionDone)

        protocol.dataReceived(b"+ Something bad! and bad\r\n")

        # This should not really be logged.  See #6021.
        logged = self.flushLoggedErrors(imap4.IllegalServerResponse)
        self.assertEqual(len(logged), 1)
        self.assertEqual(logged[0].value.args[0], b"Something bad! and bad")
        return d


class PreauthIMAP4ClientMixin:
    """
    Mixin for L{SynchronousTestCase} subclasses which
    provides a C{setUp} method which creates an L{IMAP4Client}
    connected to a L{StringTransport} and puts it into the
    I{authenticated} state.

    @ivar transport: A L{StringTransport} to which C{client} is
        connected.

    @ivar client: An L{IMAP4Client} which is connected to
        C{transport}.
    """

    clientProtocol: Type[imap4.IMAP4Client] = imap4.IMAP4Client

    def setUp(self):
        """
        Create an IMAP4Client connected to a fake transport and in the
        authenticated state.
        """
        self.transport = StringTransport()
        self.client = self.clientProtocol()
        self.client.makeConnection(self.transport)
        self.client.dataReceived(b"* PREAUTH Hello unittest\r\n")


class SelectionTestsMixin(PreauthIMAP4ClientMixin):
    """
    Mixin for test cases which defines tests which apply to both I{EXAMINE} and
    I{SELECT} support.
    """

    def _examineOrSelect(self):
        """
        Issue either an I{EXAMINE} or I{SELECT} command (depending on
        C{self.method}), assert that the correct bytes are written to the
        transport, and return the L{Deferred} returned by whichever method was
        called.
        """
        d = getattr(self.client, self.method)("foobox")
        self.assertEqual(
            self.transport.value(), b"0001 " + self.command + b" foobox\r\n"
        )
        return d

    def _response(self, *lines):
        """
        Deliver the given (unterminated) response lines to C{self.client} and
        then deliver a tagged SELECT or EXAMINE completion line to finish the
        SELECT or EXAMINE response.
        """
        for line in lines:
            self.client.dataReceived(line + b"\r\n")
        self.client.dataReceived(
            b"0001 OK [READ-ONLY] " + self.command + b" completed\r\n"
        )

    def test_exists(self):
        """
        If the server response to a I{SELECT} or I{EXAMINE} command includes an
        I{EXISTS} response, the L{Deferred} return by L{IMAP4Client.select} or
        L{IMAP4Client.examine} fires with a C{dict} including the value
        associated with the C{'EXISTS'} key.
        """
        d = self._examineOrSelect()
        self._response(b"* 3 EXISTS")
        self.assertEqual(self.successResultOf(d), {"READ-WRITE": False, "EXISTS": 3})

    def test_nonIntegerExists(self):
        """
        If the server returns a non-integer EXISTS value in its response to a
        I{SELECT} or I{EXAMINE} command, the L{Deferred} returned by
        L{IMAP4Client.select} or L{IMAP4Client.examine} fails with
        L{IllegalServerResponse}.
        """
        d = self._examineOrSelect()
        self._response(b"* foo EXISTS")
        self.failureResultOf(d, imap4.IllegalServerResponse)

    def test_recent(self):
        """
        If the server response to a I{SELECT} or I{EXAMINE} command includes an
        I{RECENT} response, the L{Deferred} return by L{IMAP4Client.select} or
        L{IMAP4Client.examine} fires with a C{dict} including the value
        associated with the C{'RECENT'} key.
        """
        d = self._examineOrSelect()
        self._response(b"* 5 RECENT")
        self.assertEqual(self.successResultOf(d), {"READ-WRITE": False, "RECENT": 5})

    def test_nonIntegerRecent(self):
        """
        If the server returns a non-integer RECENT value in its response to a
        I{SELECT} or I{EXAMINE} command, the L{Deferred} returned by
        L{IMAP4Client.select} or L{IMAP4Client.examine} fails with
        L{IllegalServerResponse}.
        """
        d = self._examineOrSelect()
        self._response(b"* foo RECENT")
        self.failureResultOf(d, imap4.IllegalServerResponse)

    def test_unseen(self):
        """
        If the server response to a I{SELECT} or I{EXAMINE} command includes an
        I{UNSEEN} response, the L{Deferred} returned by L{IMAP4Client.select} or
        L{IMAP4Client.examine} fires with a C{dict} including the value
        associated with the C{'UNSEEN'} key.
        """
        d = self._examineOrSelect()
        self._response(b"* OK [UNSEEN 8] Message 8 is first unseen")
        self.assertEqual(self.successResultOf(d), {"READ-WRITE": False, "UNSEEN": 8})

    def test_nonIntegerUnseen(self):
        """
        If the server returns a non-integer UNSEEN value in its response to a
        I{SELECT} or I{EXAMINE} command, the L{Deferred} returned by
        L{IMAP4Client.select} or L{IMAP4Client.examine} fails with
        L{IllegalServerResponse}.
        """
        d = self._examineOrSelect()
        self._response(b"* OK [UNSEEN foo] Message foo is first unseen")
        self.failureResultOf(d, imap4.IllegalServerResponse)

    def test_uidvalidity(self):
        """
        If the server response to a I{SELECT} or I{EXAMINE} command includes an
        I{UIDVALIDITY} response, the L{Deferred} returned by
        L{IMAP4Client.select} or L{IMAP4Client.examine} fires with a C{dict}
        including the value associated with the C{'UIDVALIDITY'} key.
        """
        d = self._examineOrSelect()
        self._response(b"* OK [UIDVALIDITY 12345] UIDs valid")
        self.assertEqual(
            self.successResultOf(d), {"READ-WRITE": False, "UIDVALIDITY": 12345}
        )

    def test_nonIntegerUIDVALIDITY(self):
        """
        If the server returns a non-integer UIDVALIDITY value in its response to
        a I{SELECT} or I{EXAMINE} command, the L{Deferred} returned by
        L{IMAP4Client.select} or L{IMAP4Client.examine} fails with
        L{IllegalServerResponse}.
        """
        d = self._examineOrSelect()
        self._response(b"* OK [UIDVALIDITY foo] UIDs valid")
        self.failureResultOf(d, imap4.IllegalServerResponse)

    def test_uidnext(self):
        """
        If the server response to a I{SELECT} or I{EXAMINE} command includes an
        I{UIDNEXT} response, the L{Deferred} returned by L{IMAP4Client.select}
        or L{IMAP4Client.examine} fires with a C{dict} including the value
        associated with the C{'UIDNEXT'} key.
        """
        d = self._examineOrSelect()
        self._response(b"* OK [UIDNEXT 4392] Predicted next UID")
        self.assertEqual(
            self.successResultOf(d), {"READ-WRITE": False, "UIDNEXT": 4392}
        )

    def test_nonIntegerUIDNEXT(self):
        """
        If the server returns a non-integer UIDNEXT value in its response to a
        I{SELECT} or I{EXAMINE} command, the L{Deferred} returned by
        L{IMAP4Client.select} or L{IMAP4Client.examine} fails with
        L{IllegalServerResponse}.
        """
        d = self._examineOrSelect()
        self._response(b"* OK [UIDNEXT foo] Predicted next UID")
        self.failureResultOf(d, imap4.IllegalServerResponse)

    def test_flags(self):
        """
        If the server response to a I{SELECT} or I{EXAMINE} command includes an
        I{FLAGS} response, the L{Deferred} returned by L{IMAP4Client.select} or
        L{IMAP4Client.examine} fires with a C{dict} including the value
        associated with the C{'FLAGS'} key.
        """
        d = self._examineOrSelect()
        self._response(b"* FLAGS (\\Answered \\Flagged \\Deleted \\Seen \\Draft)")
        self.assertEqual(
            self.successResultOf(d),
            {
                "READ-WRITE": False,
                "FLAGS": ("\\Answered", "\\Flagged", "\\Deleted", "\\Seen", "\\Draft"),
            },
        )

    def test_permanentflags(self):
        """
        If the server response to a I{SELECT} or I{EXAMINE} command includes an
        I{FLAGS} response, the L{Deferred} returned by L{IMAP4Client.select} or
        L{IMAP4Client.examine} fires with a C{dict} including the value
        associated with the C{'FLAGS'} key.
        """
        d = self._examineOrSelect()
        self._response(
            b"* OK [PERMANENTFLAGS (\\Starred)] Just one permanent flag in "
            b"that list up there"
        )
        self.assertEqual(
            self.successResultOf(d),
            {"READ-WRITE": False, "PERMANENTFLAGS": ("\\Starred",)},
        )

    def test_unrecognizedOk(self):
        """
        If the server response to a I{SELECT} or I{EXAMINE} command includes an
        I{OK} with unrecognized response code text, parsing does not fail.
        """
        d = self._examineOrSelect()
        self._response(b"* OK [X-MADE-UP] I just made this response text up.")
        # The value won't show up in the result.  It would be okay if it did
        # someday, perhaps.  This shouldn't ever happen, though.
        self.assertEqual(self.successResultOf(d), {"READ-WRITE": False})

    def test_bareOk(self):
        """
        If the server response to a I{SELECT} or I{EXAMINE} command includes an
        I{OK} with no response code text, parsing does not fail.
        """
        d = self._examineOrSelect()
        self._response(b"* OK")
        self.assertEqual(self.successResultOf(d), {"READ-WRITE": False})


class IMAP4ClientExamineTests(SelectionTestsMixin, SynchronousTestCase):
    """
    Tests for the L{IMAP4Client.examine} method.

    An example of usage of the EXAMINE command from RFC 3501, section 6.3.2::

        S: * 17 EXISTS
        S: * 2 RECENT
        S: * OK [UNSEEN 8] Message 8 is first unseen
        S: * OK [UIDVALIDITY 3857529045] UIDs valid
        S: * OK [UIDNEXT 4392] Predicted next UID
        S: * FLAGS (\\Answered \\Flagged \\Deleted \\Seen \\Draft)
        S: * OK [PERMANENTFLAGS ()] No permanent flags permitted
        S: A932 OK [READ-ONLY] EXAMINE completed
    """

    method = "examine"
    command = b"EXAMINE"


class IMAP4ClientSelectTests(SelectionTestsMixin, SynchronousTestCase):
    r"""
    Tests for the L{IMAP4Client.select} method.

    An example of usage of the SELECT command from RFC 3501, section 6.3.1::

        C: A142 SELECT INBOX
        S: * 172 EXISTS
        S: * 1 RECENT
        S: * OK [UNSEEN 12] Message 12 is first unseen
        S: * OK [UIDVALIDITY 3857529045] UIDs valid
        S: * OK [UIDNEXT 4392] Predicted next UID
        S: * FLAGS (\Answered \Flagged \Deleted \Seen \Draft)
        S: * OK [PERMANENTFLAGS (\Deleted \Seen \*)] Limited
        S: A142 OK [READ-WRITE] SELECT completed
    """

    method = "select"
    command = b"SELECT"


class IMAP4ClientExpungeTests(PreauthIMAP4ClientMixin, SynchronousTestCase):
    """
    Tests for the L{IMAP4Client.expunge} method.

    An example of usage of the EXPUNGE command from RFC 3501, section 6.4.3::

        C: A202 EXPUNGE
        S: * 3 EXPUNGE
        S: * 3 EXPUNGE
        S: * 5 EXPUNGE
        S: * 8 EXPUNGE
        S: A202 OK EXPUNGE completed
    """

    def _expunge(self):
        d = self.client.expunge()
        self.assertEqual(self.transport.value(), b"0001 EXPUNGE\r\n")
        self.transport.clear()
        return d

    def _response(self, sequenceNumbers):
        for number in sequenceNumbers:
            self.client.lineReceived(networkString(f"* {number} EXPUNGE"))
        self.client.lineReceived(b"0001 OK EXPUNGE COMPLETED")

    def test_expunge(self):
        """
        L{IMAP4Client.expunge} sends the I{EXPUNGE} command and returns a
        L{Deferred} which fires with a C{list} of message sequence numbers
        given by the server's response.
        """
        d = self._expunge()
        self._response([3, 3, 5, 8])
        self.assertEqual(self.successResultOf(d), [3, 3, 5, 8])

    def test_nonIntegerExpunged(self):
        """
        If the server responds with a non-integer where a message sequence
        number is expected, the L{Deferred} returned by L{IMAP4Client.expunge}
        fails with L{IllegalServerResponse}.
        """
        d = self._expunge()
        self._response([3, 3, "foo", 8])
        self.failureResultOf(d, imap4.IllegalServerResponse)


class IMAP4ClientSearchTests(PreauthIMAP4ClientMixin, SynchronousTestCase):
    """
    Tests for the L{IMAP4Client.search} method.

    An example of usage of the SEARCH command from RFC 3501, section 6.4.4::

        C: A282 SEARCH FLAGGED SINCE 1-Feb-1994 NOT FROM "Smith"
        S: * SEARCH 2 84 882
        S: A282 OK SEARCH completed
        C: A283 SEARCH TEXT "string not in mailbox"
        S: * SEARCH
        S: A283 OK SEARCH completed
        C: A284 SEARCH CHARSET UTF-8 TEXT {6}
        C: XXXXXX
        S: * SEARCH 43
        S: A284 OK SEARCH completed
    """

    def _search(self):
        d = self.client.search(imap4.Query(text="ABCDEF"))
        self.assertEqual(self.transport.value(), b'0001 SEARCH (TEXT "ABCDEF")\r\n')
        return d

    def _response(self, messageNumbers):
        self.client.lineReceived(
            b"* SEARCH " + networkString(" ".join(map(str, messageNumbers)))
        )
        self.client.lineReceived(b"0001 OK SEARCH completed")

    def test_search(self):
        """
        L{IMAP4Client.search} sends the I{SEARCH} command and returns a
        L{Deferred} which fires with a C{list} of message sequence numbers
        given by the server's response.
        """
        d = self._search()
        self._response([2, 5, 10])
        self.assertEqual(self.successResultOf(d), [2, 5, 10])

    def test_nonIntegerFound(self):
        """
        If the server responds with a non-integer where a message sequence
        number is expected, the L{Deferred} returned by L{IMAP4Client.search}
        fails with L{IllegalServerResponse}.
        """
        d = self._search()
        self._response([2, "foo", 10])
        self.failureResultOf(d, imap4.IllegalServerResponse)


class IMAP4ClientFetchTests(PreauthIMAP4ClientMixin, SynchronousTestCase):
    """
    Tests for the L{IMAP4Client.fetch} method.

    See RFC 3501, section 6.4.5.
    """

    def test_fetchUID(self):
        """
        L{IMAP4Client.fetchUID} sends the I{FETCH UID} command and returns a
        L{Deferred} which fires with a C{dict} mapping message sequence numbers
        to C{dict}s mapping C{'UID'} to that message's I{UID} in the server's
        response.
        """
        d = self.client.fetchUID("1:7")
        self.assertEqual(self.transport.value(), b"0001 FETCH 1:7 (UID)\r\n")
        self.client.lineReceived(b"* 2 FETCH (UID 22)")
        self.client.lineReceived(b"* 3 FETCH (UID 23)")
        self.client.lineReceived(b"* 4 FETCH (UID 24)")
        self.client.lineReceived(b"* 5 FETCH (UID 25)")
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.assertEqual(
            self.successResultOf(d),
            {2: {"UID": "22"}, 3: {"UID": "23"}, 4: {"UID": "24"}, 5: {"UID": "25"}},
        )

    def test_fetchUIDNonIntegerFound(self):
        """
        If the server responds with a non-integer where a message sequence
        number is expected, the L{Deferred} returned by L{IMAP4Client.fetchUID}
        fails with L{IllegalServerResponse}.
        """
        d = self.client.fetchUID("1")
        self.assertEqual(self.transport.value(), b"0001 FETCH 1 (UID)\r\n")
        self.client.lineReceived(b"* foo FETCH (UID 22)")
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.failureResultOf(d, imap4.IllegalServerResponse)

    def test_incompleteFetchUIDResponse(self):
        """
        If the server responds with an incomplete I{FETCH} response line, the
        L{Deferred} returned by L{IMAP4Client.fetchUID} fails with
        L{IllegalServerResponse}.
        """
        d = self.client.fetchUID("1:7")
        self.assertEqual(self.transport.value(), b"0001 FETCH 1:7 (UID)\r\n")
        self.client.lineReceived(b"* 2 FETCH (UID 22)")
        self.client.lineReceived(b"* 3 FETCH (UID)")
        self.client.lineReceived(b"* 4 FETCH (UID 24)")
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.failureResultOf(d, imap4.IllegalServerResponse)

    def test_fetchBody(self):
        """
        L{IMAP4Client.fetchBody} sends the I{FETCH BODY} command and returns a
        L{Deferred} which fires with a C{dict} mapping message sequence numbers
        to C{dict}s mapping C{'RFC822.TEXT'} to that message's body as given in
        the server's response.
        """
        d = self.client.fetchBody("3")
        self.assertEqual(self.transport.value(), b"0001 FETCH 3 (RFC822.TEXT)\r\n")
        self.client.lineReceived(b'* 3 FETCH (RFC822.TEXT "Message text")')
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.assertEqual(self.successResultOf(d), {3: {"RFC822.TEXT": "Message text"}})

    def test_fetchSpecific(self):
        """
        L{IMAP4Client.fetchSpecific} sends the I{BODY[]} command if no
        parameters beyond the message set to retrieve are given.  It returns a
        L{Deferred} which fires with a C{dict} mapping message sequence numbers
        to C{list}s of corresponding message data given by the server's
        response.
        """
        d = self.client.fetchSpecific("7")
        self.assertEqual(self.transport.value(), b"0001 FETCH 7 BODY[]\r\n")
        self.client.lineReceived(b'* 7 FETCH (BODY[] "Some body")')
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.assertEqual(self.successResultOf(d), {7: [["BODY", [], "Some body"]]})

    def test_fetchSpecificPeek(self):
        """
        L{IMAP4Client.fetchSpecific} issues a I{BODY.PEEK[]} command if passed
        C{True} for the C{peek} parameter.
        """
        d = self.client.fetchSpecific("6", peek=True)
        self.assertEqual(self.transport.value(), b"0001 FETCH 6 BODY.PEEK[]\r\n")
        # BODY.PEEK responses are just BODY
        self.client.lineReceived(b'* 6 FETCH (BODY[] "Some body")')
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.assertEqual(self.successResultOf(d), {6: [["BODY", [], "Some body"]]})

    def test_fetchSpecificNumbered(self):
        """
        L{IMAP4Client.fetchSpecific}, when passed a sequence for
        C{headerNumber}, sends the I{BODY[N.M]} command.  It returns a
        L{Deferred} which fires with a C{dict} mapping message sequence numbers
        to C{list}s of corresponding message data given by the server's
        response.
        """
        d = self.client.fetchSpecific("7", headerNumber=(1, 2, 3))
        self.assertEqual(self.transport.value(), b"0001 FETCH 7 BODY[1.2.3]\r\n")
        self.client.lineReceived(b'* 7 FETCH (BODY[1.2.3] "Some body")')
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.assertEqual(
            self.successResultOf(d), {7: [["BODY", ["1.2.3"], "Some body"]]}
        )

    def test_fetchSpecificText(self):
        """
        L{IMAP4Client.fetchSpecific}, when passed C{'TEXT'} for C{headerType},
        sends the I{BODY[TEXT]} command.  It returns a L{Deferred} which fires
        with a C{dict} mapping message sequence numbers to C{list}s of
        corresponding message data given by the server's response.
        """
        d = self.client.fetchSpecific("8", headerType="TEXT")
        self.assertEqual(self.transport.value(), b"0001 FETCH 8 BODY[TEXT]\r\n")
        self.client.lineReceived(b'* 8 FETCH (BODY[TEXT] "Some body")')
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.assertEqual(
            self.successResultOf(d), {8: [["BODY", ["TEXT"], "Some body"]]}
        )

    def test_fetchSpecificNumberedText(self):
        """
        If passed a value for the C{headerNumber} parameter and C{'TEXT'} for
        the C{headerType} parameter, L{IMAP4Client.fetchSpecific} sends a
        I{BODY[number.TEXT]} request and returns a L{Deferred} which fires with
        a C{dict} mapping message sequence numbers to C{list}s of message data
        given by the server's response.
        """
        d = self.client.fetchSpecific("4", headerType="TEXT", headerNumber=7)
        self.assertEqual(self.transport.value(), b"0001 FETCH 4 BODY[7.TEXT]\r\n")
        self.client.lineReceived(b'* 4 FETCH (BODY[7.TEXT] "Some body")')
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.assertEqual(
            self.successResultOf(d), {4: [["BODY", ["7.TEXT"], "Some body"]]}
        )

    def test_incompleteFetchSpecificTextResponse(self):
        """
        If the server responds to a I{BODY[TEXT]} request with a I{FETCH} line
        which is truncated after the I{BODY[TEXT]} tokens, the L{Deferred}
        returned by L{IMAP4Client.fetchUID} fails with
        L{IllegalServerResponse}.
        """
        d = self.client.fetchSpecific("8", headerType="TEXT")
        self.assertEqual(self.transport.value(), b"0001 FETCH 8 BODY[TEXT]\r\n")
        self.client.lineReceived(b"* 8 FETCH (BODY[TEXT])")
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.failureResultOf(d, imap4.IllegalServerResponse)

    def test_fetchSpecificMIME(self):
        """
        L{IMAP4Client.fetchSpecific}, when passed C{'MIME'} for C{headerType},
        sends the I{BODY[MIME]} command.  It returns a L{Deferred} which fires
        with a C{dict} mapping message sequence numbers to C{list}s of
        corresponding message data given by the server's response.
        """
        d = self.client.fetchSpecific("8", headerType="MIME")
        self.assertEqual(self.transport.value(), b"0001 FETCH 8 BODY[MIME]\r\n")
        self.client.lineReceived(b'* 8 FETCH (BODY[MIME] "Some body")')
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.assertEqual(
            self.successResultOf(d), {8: [["BODY", ["MIME"], "Some body"]]}
        )

    def test_fetchSpecificPartial(self):
        """
        L{IMAP4Client.fetchSpecific}, when passed C{offset} and C{length},
        sends a partial content request (like I{BODY[TEXT]<offset.length>}).
        It returns a L{Deferred} which fires with a C{dict} mapping message
        sequence numbers to C{list}s of corresponding message data given by the
        server's response.
        """
        d = self.client.fetchSpecific("9", headerType="TEXT", offset=17, length=3)
        self.assertEqual(self.transport.value(), b"0001 FETCH 9 BODY[TEXT]<17.3>\r\n")
        self.client.lineReceived(b'* 9 FETCH (BODY[TEXT]<17> "foo")')
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.assertEqual(
            self.successResultOf(d), {9: [["BODY", ["TEXT"], "<17>", "foo"]]}
        )

    def test_incompleteFetchSpecificPartialResponse(self):
        """
        If the server responds to a I{BODY[TEXT]} request with a I{FETCH} line
        which is truncated after the I{BODY[TEXT]<offset>} tokens, the
        L{Deferred} returned by L{IMAP4Client.fetchUID} fails with
        L{IllegalServerResponse}.
        """
        d = self.client.fetchSpecific("8", headerType="TEXT")
        self.assertEqual(self.transport.value(), b"0001 FETCH 8 BODY[TEXT]\r\n")
        self.client.lineReceived(b"* 8 FETCH (BODY[TEXT]<17>)")
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.failureResultOf(d, imap4.IllegalServerResponse)

    def test_fetchSpecificHTML(self):
        """
        If the body of a message begins with I{<} and ends with I{>} (as,
        for example, HTML bodies typically will), this is still interpreted
        as the body by L{IMAP4Client.fetchSpecific} (and particularly, not
        as a length indicator for a response to a request for a partial
        body).
        """
        d = self.client.fetchSpecific("7")
        self.assertEqual(self.transport.value(), b"0001 FETCH 7 BODY[]\r\n")
        self.client.lineReceived(b'* 7 FETCH (BODY[] "<html>test</html>")')
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.assertEqual(
            self.successResultOf(d), {7: [["BODY", [], "<html>test</html>"]]}
        )

    def assertFetchSpecificFieldsWithEmptyList(self, section):
        """
        Assert that the provided C{BODY} section, when invoked with no
        arguments, produces an empty list, and that it returns a
        L{Deferred} which fires with a C{dict} mapping message
        sequence numbers to C{list}s of corresponding message data
        given by the server's response.

        @param section: The C{BODY} section to test: either
            C{'HEADER.FIELDS'} or C{'HEADER.FIELDS.NOT'}
        @type section: L{str}
        """
        d = self.client.fetchSpecific("10", headerType=section)
        self.assertEqual(
            self.transport.value(),
            b"0001 FETCH 10 BODY[" + section.encode("ascii") + b" ()]\r\n",
        )
        # It's unclear what the response would look like - would it be
        # an empty string?  No IMAP server parses an empty list of headers
        self.client.lineReceived(
            b"* 10 FETCH (BODY[" + section.encode("ascii") + b' ()] "")'
        )
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.assertEqual(self.successResultOf(d), {10: [["BODY", [section, []], ""]]})

    def test_fetchSpecificHeaderFieldsWithoutHeaders(self):
        """
        L{IMAP4Client.fetchSpecific}, when passed C{'HEADER.FIELDS'}
        for C{headerType} but no C{headerArgs}, sends the
        I{BODY[HEADER.FIELDS]} command with no arguments.  It returns
        a L{Deferred} which fires with a C{dict} mapping message
        sequence numbers to C{list}s of corresponding message data
        given by the server's response.
        """
        self.assertFetchSpecificFieldsWithEmptyList("HEADER.FIELDS")

    def test_fetchSpecificHeaderFieldsNotWithoutHeaders(self):
        """
        L{IMAP4Client.fetchSpecific}, when passed
        C{'HEADER.FIELDS.NOT'} for C{headerType} but no C{headerArgs},
        sends the I{BODY[HEADER.FIELDS.NOT]} command with no
        arguments.  It returns a L{Deferred} which fires with a
        C{dict} mapping message sequence numbers to C{list}s of
        corresponding message data given by the server's response.
        """
        self.assertFetchSpecificFieldsWithEmptyList("HEADER.FIELDS.NOT")

    def test_fetchSpecificHeader(self):
        """
        L{IMAP4Client.fetchSpecific}, when passed C{'HEADER'} for
        C{headerType}, sends the I{BODY[HEADER]} command.  It returns
        a L{Deferred} which fires with a C{dict} mapping message
        sequence numbers to C{list}s of corresponding message data
        given by the server's response.
        """
        d = self.client.fetchSpecific("11", headerType="HEADER")
        self.assertEqual(self.transport.value(), b"0001 FETCH 11 BODY[HEADER]\r\n")
        self.client.lineReceived(
            b"* 11 FETCH (BODY[HEADER]"
            b' "From: someone@localhost\r\nSubject: Some subject")'
        )
        self.client.lineReceived(b"0001 OK FETCH completed")
        self.assertEqual(
            self.successResultOf(d),
            {
                11: [
                    [
                        "BODY",
                        ["HEADER"],
                        "From: someone@localhost\r\nSubject: Some subject",
                    ]
                ]
            },
        )


class IMAP4ClientStoreTests(PreauthIMAP4ClientMixin, TestCase):
    r"""
    Tests for the L{IMAP4Client.setFlags}, L{IMAP4Client.addFlags}, and
    L{IMAP4Client.removeFlags} methods.

    An example of usage of the STORE command, in terms of which these three
    methods are implemented, from RFC 3501, section 6.4.6::

        C: A003 STORE 2:4 +FLAGS (\Deleted)
        S: * 2 FETCH (FLAGS (\Deleted \Seen))
        S: * 3 FETCH (FLAGS (\Deleted))
        S: * 4 FETCH (FLAGS (\Deleted \Flagged \Seen))
        S: A003 OK STORE completed
    """

    clientProtocol = StillSimplerClient

    def _flagsTest(self, method, item):
        """
        Test a non-silent flag modifying method.  Call the method, assert that
        the correct bytes are sent, deliver a I{FETCH} response, and assert
        that the result of the Deferred returned by the method is correct.

        @param method: The name of the method to test.
        @param item: The data item which is expected to be specified.
        """
        d = getattr(self.client, method)("3", ("\\Read", "\\Seen"), False)
        self.assertEqual(
            self.transport.value(), b"0001 STORE 3 " + item + b" (\\Read \\Seen)\r\n"
        )
        self.client.lineReceived(b"* 3 FETCH (FLAGS (\\Read \\Seen))")
        self.client.lineReceived(b"0001 OK STORE completed")
        self.assertEqual(self.successResultOf(d), {3: {"FLAGS": ["\\Read", "\\Seen"]}})

    def _flagsSilentlyTest(self, method, item):
        """
        Test a silent flag modifying method.  Call the method, assert that the
        correct bytes are sent, deliver an I{OK} response, and assert that the
        result of the Deferred returned by the method is correct.

        @param method: The name of the method to test.
        @param item: The data item which is expected to be specified.
        """
        d = getattr(self.client, method)("3", ("\\Read", "\\Seen"), True)
        self.assertEqual(
            self.transport.value(), b"0001 STORE 3 " + item + b" (\\Read \\Seen)\r\n"
        )
        self.client.lineReceived(b"0001 OK STORE completed")
        self.assertEqual(self.successResultOf(d), {})

    def _flagsSilentlyWithUnsolicitedDataTest(self, method, item):
        """
        Test unsolicited data received in response to a silent flag modifying
        method.  Call the method, assert that the correct bytes are sent,
        deliver the unsolicited I{FETCH} response, and assert that the result
        of the Deferred returned by the method is correct.

        @param method: The name of the method to test.
        @param item: The data item which is expected to be specified.
        """
        d = getattr(self.client, method)("3", ("\\Read", "\\Seen"), True)
        self.assertEqual(
            self.transport.value(), b"0001 STORE 3 " + item + b" (\\Read \\Seen)\r\n"
        )
        self.client.lineReceived(b"* 2 FETCH (FLAGS (\\Read \\Seen))")
        self.client.lineReceived(b"0001 OK STORE completed")
        self.assertEqual(self.successResultOf(d), {})
        self.assertEqual(self.client.flags, {2: ["\\Read", "\\Seen"]})

    def test_setFlags(self):
        """
        When passed a C{False} value for the C{silent} parameter,
        L{IMAP4Client.setFlags} sends the I{STORE} command with a I{FLAGS} data
        item and returns a L{Deferred} which fires with a C{dict} mapping
        message sequence numbers to C{dict}s mapping C{'FLAGS'} to the new
        flags of those messages.
        """
        self._flagsTest("setFlags", b"FLAGS")

    def test_setFlagsSilently(self):
        """
        When passed a C{True} value for the C{silent} parameter,
        L{IMAP4Client.setFlags} sends the I{STORE} command with a
        I{FLAGS.SILENT} data item and returns a L{Deferred} which fires with an
        empty dictionary.
        """
        self._flagsSilentlyTest("setFlags", b"FLAGS.SILENT")

    def test_setFlagsSilentlyWithUnsolicitedData(self):
        """
        If unsolicited flag data is received in response to a I{STORE}
        I{FLAGS.SILENT} request, that data is passed to the C{flagsChanged}
        callback.
        """
        self._flagsSilentlyWithUnsolicitedDataTest("setFlags", b"FLAGS.SILENT")

    def test_addFlags(self):
        """
        L{IMAP4Client.addFlags} is like L{IMAP4Client.setFlags}, but sends
        I{+FLAGS} instead of I{FLAGS}.
        """
        self._flagsTest("addFlags", b"+FLAGS")

    def test_addFlagsSilently(self):
        """
        L{IMAP4Client.addFlags} with a C{True} value for C{silent} behaves like
        L{IMAP4Client.setFlags} with a C{True} value for C{silent}, but it
        sends I{+FLAGS.SILENT} instead of I{FLAGS.SILENT}.
        """
        self._flagsSilentlyTest("addFlags", b"+FLAGS.SILENT")

    def test_addFlagsSilentlyWithUnsolicitedData(self):
        """
        L{IMAP4Client.addFlags} behaves like L{IMAP4Client.setFlags} when used
        in silent mode and unsolicited data is received.
        """
        self._flagsSilentlyWithUnsolicitedDataTest("addFlags", b"+FLAGS.SILENT")

    def test_removeFlags(self):
        """
        L{IMAP4Client.removeFlags} is like L{IMAP4Client.setFlags}, but sends
        I{-FLAGS} instead of I{FLAGS}.
        """
        self._flagsTest("removeFlags", b"-FLAGS")

    def test_removeFlagsSilently(self):
        """
        L{IMAP4Client.removeFlags} with a C{True} value for C{silent} behaves
        like L{IMAP4Client.setFlags} with a C{True} value for C{silent}, but it
        sends I{-FLAGS.SILENT} instead of I{FLAGS.SILENT}.
        """
        self._flagsSilentlyTest("removeFlags", b"-FLAGS.SILENT")

    def test_removeFlagsSilentlyWithUnsolicitedData(self):
        """
        L{IMAP4Client.removeFlags} behaves like L{IMAP4Client.setFlags} when
        used in silent mode and unsolicited data is received.
        """
        self._flagsSilentlyWithUnsolicitedDataTest("removeFlags", b"-FLAGS.SILENT")


class IMAP4ClientStatusTests(PreauthIMAP4ClientMixin, SynchronousTestCase):
    """
    Tests for the L{IMAP4Client.status} method.

    An example of usage of the STATUS command from RFC 3501, section
    5.1.2::

        C: A042 STATUS blurdybloop (UIDNEXT MESSAGES)
        S: * STATUS blurdybloop (MESSAGES 231 UIDNEXT 44292)
        S: A042 OK STATUS completed

    @see: U{https://tools.ietf.org/html/rfc3501#section-5.1.2}
    """

    def testUnknownName(self):
        """
        Only allow sending the C{STATUS} names defined in RFC 3501.

        @see: U{https://tools.ietf.org/html/rfc3501#section-5.1.2}
        """
        exc = self.assertRaises(
            ValueError,
            self.client.status,
            "ignored",
            "IMPOSSIBLE?!",
        )
        self.assertEqual(str(exc), "Unknown names: " + repr({"IMPOSSIBLE?!"}))

    def testUndecodableName(self):
        """
        C{STATUS} names that cannot be decoded as ASCII cause the
        status Deferred to fail with L{IllegalServerResponse}
        """

        d = self.client.status("blurdybloop", "MESSAGES")
        self.assertEqual(
            self.transport.value(),
            b"0001 STATUS blurdybloop (MESSAGES)\r\n",
        )

        self.client.lineReceived(
            b"* STATUS blurdybloop " b'(MESSAGES 1 ASCIINAME "OK" NOT\xffASCII "NO")'
        )
        self.client.lineReceived(b"0001 OK STATUS completed")
        self.failureResultOf(d, imap4.IllegalServerResponse)


class IMAP4ClientCopyTests(PreauthIMAP4ClientMixin, SynchronousTestCase):
    """
    Tests for the L{IMAP4Client.copy} method.

    An example of the C{COPY} command, which this method implements,
    from RFC 3501, section 6.4.7::

        C: A003 COPY 2:4 MEETING
        S: A003 OK COPY completed
    """

    clientProtocol = StillSimplerClient

    def test_copySequenceNumbers(self):
        """
        L{IMAP4Client.copy} copies the messages identified by their
        sequence numbers to the mailbox, returning a L{Deferred} that
        succeeds with a true value.
        """
        d = self.client.copy("2:3", "MEETING", uid=False)

        self.assertEqual(
            self.transport.value(),
            b"0001 COPY 2:3 MEETING\r\n",
        )

        self.client.lineReceived(b"0001 OK COPY completed")
        self.assertEqual(self.successResultOf(d), ([], b"OK COPY completed"))

    def test_copySequenceNumbersFails(self):
        """
        L{IMAP4Client.copy} returns a L{Deferred} that fails with an
        L{IMAP4Exception} when the messages specified by the given
        sequence numbers could not be copied to the mailbox.
        """
        d = self.client.copy("2:3", "MEETING", uid=False)

        self.assertEqual(
            self.transport.value(),
            b"0001 COPY 2:3 MEETING\r\n",
        )

        self.client.lineReceived(b"0001 BAD COPY failed")
        self.assertIsInstance(self.failureResultOf(d).value, imap4.IMAP4Exception)

    def test_copyUIDs(self):
        """
        L{IMAP4Client.copy} copies the messages identified by their
        UIDs to the mailbox, returning a L{Deferred} that succeeds
        with a true value.
        """
        d = self.client.copy("2:3", "MEETING", uid=True)

        self.assertEqual(
            self.transport.value(),
            b"0001 UID COPY 2:3 MEETING\r\n",
        )

        self.client.lineReceived(b"0001 OK COPY completed")
        self.assertEqual(self.successResultOf(d), ([], b"OK COPY completed"))

    def test_copyUIDsFails(self):
        """
        L{IMAP4Client.copy} returns a L{Deferred} that fails with an
        L{IMAP4Exception} when the messages specified by the given
        UIDs could not be copied to the mailbox.
        """
        d = self.client.copy("2:3", "MEETING", uid=True)

        self.assertEqual(
            self.transport.value(),
            b"0001 UID COPY 2:3 MEETING\r\n",
        )

        self.client.lineReceived(b"0001 BAD COPY failed")
        self.assertIsInstance(self.failureResultOf(d).value, imap4.IMAP4Exception)


class FakeyServer(imap4.IMAP4Server):
    state = "select"
    timeout = None

    def sendServerGreeting(self):
        pass


@implementer(imap4.IMessage)
class FakeyMessage(util.FancyStrMixin):
    showAttributes = ("headers", "flags", "date", "_body", "uid")

    def __init__(self, headers, flags, date, body, uid, subpart):
        self.headers = headers
        self.flags = flags
        self._body = body
        self.size = len(body)
        self.date = date
        self.uid = uid
        self.subpart = subpart

    def getHeaders(self, negate, *names):
        self.got_headers = negate, names
        return self.headers

    def getFlags(self):
        return self.flags

    def getInternalDate(self):
        return self.date

    def getBodyFile(self):
        return BytesIO(self._body)

    def getSize(self):
        return self.size

    def getUID(self):
        return self.uid

    def isMultipart(self):
        return self.subpart is not None

    def getSubPart(self, part):
        self.got_subpart = part
        return self.subpart[part]


class NewStoreTests(TestCase, IMAP4HelperMixin):
    result = None
    storeArgs = None

    def setUp(self):
        self.received_messages = self.received_uid = None

        self.server = imap4.IMAP4Server()
        self.server.state = "select"
        self.server.mbox = self
        self.connected = defer.Deferred()
        self.client = SimpleClient(self.connected)

    def addListener(self, x):
        pass

    def removeListener(self, x):
        pass

    def store(self, *args, **kw):
        self.storeArgs = args, kw
        return self.response

    def _storeWork(self):
        def connected():
            return self.function(self.messages, self.flags, self.silent, self.uid)

        def result(R):
            self.result = R

        self.connected.addCallback(strip(connected)).addCallback(result).addCallback(
            self._cbStopClient
        ).addErrback(self._ebGeneral)

        def check(ignored):
            self.assertEqual(self.result, self.expected)
            self.assertEqual(self.storeArgs, self.expectedArgs)

        d = loopback.loopbackTCP(self.server, self.client, noisy=False)
        d.addCallback(check)
        return d

    def testSetFlags(self, uid=0):
        self.function = self.client.setFlags
        self.messages = "1,5,9"
        self.flags = ["\\A", "\\B", "C"]
        self.silent = False
        self.uid = uid
        self.response = {
            1: ["\\A", "\\B", "C"],
            5: ["\\A", "\\B", "C"],
            9: ["\\A", "\\B", "C"],
        }
        self.expected = {
            1: {"FLAGS": ["\\A", "\\B", "C"]},
            5: {"FLAGS": ["\\A", "\\B", "C"]},
            9: {"FLAGS": ["\\A", "\\B", "C"]},
        }
        msg = imap4.MessageSet()
        msg.add(1)
        msg.add(5)
        msg.add(9)
        self.expectedArgs = ((msg, ["\\A", "\\B", "C"], 0), {"uid": 0})
        return self._storeWork()


class GetBodyStructureTests(TestCase):
    """
    Tests for L{imap4.getBodyStructure}, a helper for constructing a list which
    directly corresponds to the wire information needed for a I{BODY} or
    I{BODYSTRUCTURE} response.
    """

    def test_singlePart(self):
        """
        L{imap4.getBodyStructure} accepts a L{IMessagePart} provider and returns
        a list giving the basic fields for the I{BODY} response for that
        message.
        """
        body = b"hello, world"
        major = "image"
        minor = "jpeg"
        charset = "us-ascii"
        identifier = "some kind of id"
        description = "great justice"
        encoding = "maximum"
        msg = FakeyMessage(
            {
                "content-type": major + "/" + minor + "; charset=" + charset + "; x=y",
                "content-id": identifier,
                "content-description": description,
                "content-transfer-encoding": encoding,
            },
            (),
            b"",
            body,
            123,
            None,
        )
        structure = imap4.getBodyStructure(msg)
        self.assertEqual(
            [
                major,
                minor,
                ["charset", charset, "x", "y"],
                identifier,
                description,
                encoding,
                len(body),
            ],
            structure,
        )

    def test_emptyContentType(self):
        """
        L{imap4.getBodyStructure} returns L{None} for the major and
        minor MIME types of a L{IMessagePart} provider whose headers
        lack a C{Content-Type}, or have an empty value for it.
        """
        missing = FakeyMessage({}, (), b"", b"", 123, None)
        missingContentTypeStructure = imap4.getBodyStructure(missing)
        missingMajor, missingMinor = missingContentTypeStructure[:2]
        self.assertIs(None, missingMajor)
        self.assertIs(None, missingMinor)

        empty = FakeyMessage({"content-type": ""}, (), b"", b"", 123, None)
        emptyContentTypeStructure = imap4.getBodyStructure(empty)
        emptyMajor, emptyMinor = emptyContentTypeStructure[:2]
        self.assertIs(None, emptyMajor)
        self.assertIs(None, emptyMinor)

        newline = FakeyMessage({"content-type": "\n"}, (), b"", b"", 123, None)
        newlineContentTypeStructure = imap4.getBodyStructure(newline)
        newlineMajor, newlineMinor = newlineContentTypeStructure[:2]
        self.assertIs(None, newlineMajor)
        self.assertIs(None, newlineMinor)

    def test_onlyMajorContentType(self):
        """
        L{imap4.getBodyStructure} returns only a non-L{None} major
        MIME type for a L{IMessagePart} provider whose headers only
        have a main a C{Content-Type}.
        """
        main = FakeyMessage({"content-type": "main"}, (), b"", b"", 123, None)
        mainStructure = imap4.getBodyStructure(main)
        mainMajor, mainMinor = mainStructure[:2]
        self.assertEqual(mainMajor, "main")
        self.assertIs(mainMinor, None)

    def test_singlePartExtended(self):
        """
        L{imap4.getBodyStructure} returns a list giving the basic and extended
        fields for a I{BODYSTRUCTURE} response if passed C{True} for the
        C{extended} parameter.
        """
        body = b"hello, world"
        major = "image"
        minor = "jpeg"
        charset = "us-ascii"
        identifier = "some kind of id"
        description = "great justice"
        encoding = "maximum"
        md5 = "abcdefabcdef"
        msg = FakeyMessage(
            {
                "content-type": major + "/" + minor + "; charset=" + charset + "; x=y",
                "content-id": identifier,
                "content-description": description,
                "content-transfer-encoding": encoding,
                "content-md5": md5,
                "content-disposition": "attachment; name=foo; size=bar",
                "content-language": "fr",
                "content-location": "France",
            },
            (),
            "",
            body,
            123,
            None,
        )
        structure = imap4.getBodyStructure(msg, extended=True)
        self.assertEqual(
            [
                major,
                minor,
                ["charset", charset, "x", "y"],
                identifier,
                description,
                encoding,
                len(body),
                md5,
                ["attachment", ["name", "foo", "size", "bar"]],
                "fr",
                "France",
            ],
            structure,
        )

    def test_singlePartWithMissing(self):
        """
        For fields with no information contained in the message headers,
        L{imap4.getBodyStructure} fills in L{None} values in its result.
        """
        major = "image"
        minor = "jpeg"
        body = b"hello, world"
        msg = FakeyMessage(
            {"content-type": major + "/" + minor}, (), b"", body, 123, None
        )
        structure = imap4.getBodyStructure(msg, extended=True)
        self.assertEqual(
            [major, minor, None, None, None, None, len(body), None, None, None, None],
            structure,
        )

    def test_textPart(self):
        """
        For a I{text/*} message, the number of lines in the message body are
        included after the common single-part basic fields.
        """
        body = b"hello, world\nhow are you?\ngoodbye\n"
        major = "text"
        minor = "jpeg"
        charset = "us-ascii"
        identifier = "some kind of id"
        description = "great justice"
        encoding = "maximum"
        msg = FakeyMessage(
            {
                "content-type": major + "/" + minor + "; charset=" + charset + "; x=y",
                "content-id": identifier,
                "content-description": description,
                "content-transfer-encoding": encoding,
            },
            (),
            b"",
            body,
            123,
            None,
        )
        structure = imap4.getBodyStructure(msg)
        self.assertEqual(
            [
                major,
                minor,
                ["charset", charset, "x", "y"],
                identifier,
                description,
                encoding,
                len(body),
                len(body.splitlines()),
            ],
            structure,
        )

    def test_rfc822Message(self):
        """
        For a I{message/rfc822} message, the common basic fields are followed
        by information about the contained message.
        """
        body = b"hello, world\nhow are you?\ngoodbye\n"
        major = "text"
        minor = "jpeg"
        charset = "us-ascii"
        identifier = "some kind of id"
        description = "great justice"
        encoding = "maximum"
        msg = FakeyMessage(
            {
                "content-type": major + "/" + minor + "; charset=" + charset + "; x=y",
                "from": "Alice <alice@example.com>",
                "to": "Bob <bob@example.com>",
                "content-id": identifier,
                "content-description": description,
                "content-transfer-encoding": encoding,
            },
            (),
            "",
            body,
            123,
            None,
        )

        container = FakeyMessage(
            {
                "content-type": "message/rfc822",
            },
            (),
            b"",
            b"",
            123,
            [msg],
        )

        structure = imap4.getBodyStructure(container)
        self.assertEqual(
            [
                "message",
                "rfc822",
                None,
                None,
                None,
                None,
                0,
                imap4.getEnvelope(msg),
                imap4.getBodyStructure(msg),
                3,
            ],
            structure,
        )

    def test_multiPart(self):
        """
        For a I{multipart/*} message, L{imap4.getBodyStructure} returns a list
        containing the body structure information for each part of the message
        followed by an element giving the MIME subtype of the message.
        """
        oneSubPart = FakeyMessage(
            {
                "content-type": "image/jpeg; x=y",
                "content-id": "some kind of id",
                "content-description": "great justice",
                "content-transfer-encoding": "maximum",
            },
            (),
            b"",
            b"hello world",
            123,
            None,
        )

        anotherSubPart = FakeyMessage(
            {
                "content-type": "text/plain; charset=us-ascii",
            },
            (),
            b"",
            b"some stuff",
            321,
            None,
        )

        container = FakeyMessage(
            {
                "content-type": "multipart/related",
            },
            (),
            b"",
            b"",
            555,
            [oneSubPart, anotherSubPart],
        )

        self.assertEqual(
            [
                imap4.getBodyStructure(oneSubPart),
                imap4.getBodyStructure(anotherSubPart),
                "related",
            ],
            imap4.getBodyStructure(container),
        )

    def test_multiPartExtended(self):
        """
        When passed a I{multipart/*} message and C{True} for the C{extended}
        argument, L{imap4.getBodyStructure} includes extended structure
        information from the parts of the multipart message and extended
        structure information about the multipart message itself.
        """
        oneSubPart = FakeyMessage(
            {
                b"content-type": b"image/jpeg; x=y",
                b"content-id": b"some kind of id",
                b"content-description": b"great justice",
                b"content-transfer-encoding": b"maximum",
            },
            (),
            b"",
            b"hello world",
            123,
            None,
        )

        anotherSubPart = FakeyMessage(
            {
                b"content-type": b"text/plain; charset=us-ascii",
            },
            (),
            b"",
            b"some stuff",
            321,
            None,
        )

        container = FakeyMessage(
            {
                "content-type": "multipart/related; foo=bar",
                "content-language": "es",
                "content-location": "Spain",
                "content-disposition": "attachment; name=monkeys",
            },
            (),
            b"",
            b"",
            555,
            [oneSubPart, anotherSubPart],
        )

        self.assertEqual(
            [
                imap4.getBodyStructure(oneSubPart, extended=True),
                imap4.getBodyStructure(anotherSubPart, extended=True),
                "related",
                ["foo", "bar"],
                ["attachment", ["name", "monkeys"]],
                "es",
                "Spain",
            ],
            imap4.getBodyStructure(container, extended=True),
        )


class NewFetchTests(TestCase, IMAP4HelperMixin):
    def setUp(self):
        self.received_messages = self.received_uid = None
        self.result = None

        self.server = imap4.IMAP4Server()
        self.server.state = "select"
        self.server.mbox = self
        self.connected = defer.Deferred()
        self.client = SimpleClient(self.connected)

    def addListener(self, x):
        pass

    def removeListener(self, x):
        pass

    def fetch(self, messages, uid):
        self.received_messages = messages
        self.received_uid = uid
        return iter(zip(range(len(self.msgObjs)), self.msgObjs))

    def _fetchWork(self, uid):
        if uid:
            for (i, msg) in zip(range(len(self.msgObjs)), self.msgObjs):
                self.expected[i]["UID"] = str(msg.getUID())

        def result(R):
            self.result = R

        self.connected.addCallback(
            lambda _: self.function(self.messages, uid)
        ).addCallback(result).addCallback(self._cbStopClient).addErrback(
            self._ebGeneral
        )

        d = loopback.loopbackTCP(self.server, self.client, noisy=False)
        d.addCallback(lambda x: self.assertEqual(self.result, self.expected))
        return d

    def testFetchUID(self):
        self.function = lambda m, u: self.client.fetchUID(m)

        self.messages = "7"
        self.msgObjs = [
            FakeyMessage({}, (), b"", b"", 12345, None),
            FakeyMessage({}, (), b"", b"", 999, None),
            FakeyMessage({}, (), b"", b"", 10101, None),
        ]
        self.expected = {
            0: {"UID": "12345"},
            1: {"UID": "999"},
            2: {"UID": "10101"},
        }
        return self._fetchWork(0)

    def testFetchFlags(self, uid=0):
        self.function = self.client.fetchFlags
        self.messages = "9"
        self.msgObjs = [
            FakeyMessage({}, ["FlagA", "FlagB", "\\FlagC"], b"", b"", 54321, None),
            FakeyMessage({}, ["\\FlagC", "FlagA", "FlagB"], b"", b"", 12345, None),
        ]
        self.expected = {
            0: {"FLAGS": ["FlagA", "FlagB", "\\FlagC"]},
            1: {"FLAGS": ["\\FlagC", "FlagA", "FlagB"]},
        }
        return self._fetchWork(uid)

    def testFetchFlagsUID(self):
        return self.testFetchFlags(1)

    def testFetchInternalDate(self, uid=0):
        self.function = self.client.fetchInternalDate
        self.messages = "13"
        self.msgObjs = [
            FakeyMessage({}, (), b"Fri, 02 Nov 2003 21:25:10 GMT", b"", 23232, None),
            FakeyMessage({}, (), b"Thu, 29 Dec 2013 11:31:52 EST", b"", 101, None),
            FakeyMessage({}, (), b"Mon, 10 Mar 1992 02:44:30 CST", b"", 202, None),
            FakeyMessage({}, (), b"Sat, 11 Jan 2000 14:40:24 PST", b"", 303, None),
        ]
        self.expected = {
            0: {"INTERNALDATE": "02-Nov-2003 21:25:10 +0000"},
            1: {"INTERNALDATE": "29-Dec-2013 11:31:52 -0500"},
            2: {"INTERNALDATE": "10-Mar-1992 02:44:30 -0600"},
            3: {"INTERNALDATE": "11-Jan-2000 14:40:24 -0800"},
        }
        return self._fetchWork(uid)

    def testFetchInternalDateUID(self):
        return self.testFetchInternalDate(1)

    # if alternate locale is not available, the previous test will be skipped,
    # please install this locale for it to run.  Avoid using locale.getlocale
    # to learn the current locale; its values don't round-trip well on all
    # platforms.  Fortunately setlocale returns a value which does round-trip
    # well.
    currentLocale = locale.setlocale(locale.LC_ALL, None)
    try:
        locale.setlocale(locale.LC_ALL, "es_AR.UTF8")
    except locale.Error:
        noEsARLocale = True
    else:
        locale.setlocale(locale.LC_ALL, currentLocale)
        noEsARLocale = False

    @skipIf(noEsARLocale, "The es_AR.UTF8 locale is not installed.")
    def test_fetchInternalDateLocaleIndependent(self):
        """
        The month name in the date is locale independent.
        """
        # Fake that we're in a language where December is not Dec
        currentLocale = locale.setlocale(locale.LC_ALL, None)
        locale.setlocale(locale.LC_ALL, "es_AR.UTF8")
        self.addCleanup(locale.setlocale, locale.LC_ALL, currentLocale)
        return self.testFetchInternalDate(1)

    def testFetchEnvelope(self, uid=0):
        self.function = self.client.fetchEnvelope
        self.messages = "15"
        self.msgObjs = [
            FakeyMessage(
                {
                    "from": "user@domain",
                    "to": "resu@domain",
                    "date": "thursday",
                    "subject": "it is a message",
                    "message-id": "id-id-id-yayaya",
                },
                (),
                b"",
                b"",
                65656,
                None,
            ),
        ]
        self.expected = {
            0: {
                "ENVELOPE": [
                    "thursday",
                    "it is a message",
                    [[None, None, "user", "domain"]],
                    [[None, None, "user", "domain"]],
                    [[None, None, "user", "domain"]],
                    [[None, None, "resu", "domain"]],
                    None,
                    None,
                    None,
                    "id-id-id-yayaya",
                ]
            }
        }
        return self._fetchWork(uid)

    def testFetchEnvelopeUID(self):
        return self.testFetchEnvelope(1)

    def test_fetchBodyStructure(self, uid=0):
        """
        L{IMAP4Client.fetchBodyStructure} issues a I{FETCH BODYSTRUCTURE}
        command and returns a Deferred which fires with a structure giving the
        result of parsing the server's response.  The structure is a list
        reflecting the parenthesized data sent by the server, as described by
        RFC 3501, section 7.4.2.
        """
        self.function = self.client.fetchBodyStructure
        self.messages = "3:9,10:*"
        self.msgObjs = [
            FakeyMessage(
                {
                    "content-type": 'text/plain; name=thing; key="value"',
                    "content-id": "this-is-the-content-id",
                    "content-description": "describing-the-content-goes-here!",
                    "content-transfer-encoding": "8BIT",
                    "content-md5": "abcdef123456",
                    "content-disposition": "attachment; filename=monkeys",
                    "content-language": "es",
                    "content-location": "http://example.com/monkeys",
                },
                (),
                "",
                b"Body\nText\nGoes\nHere\n",
                919293,
                None,
            )
        ]
        self.expected = {
            0: {
                "BODYSTRUCTURE": [
                    "text",
                    "plain",
                    ["key", "value", "name", "thing"],
                    "this-is-the-content-id",
                    "describing-the-content-goes-here!",
                    "8BIT",
                    "20",
                    "4",
                    "abcdef123456",
                    ["attachment", ["filename", "monkeys"]],
                    "es",
                    "http://example.com/monkeys",
                ]
            }
        }
        return self._fetchWork(uid)

    def testFetchBodyStructureUID(self):
        """
        If passed C{True} for the C{uid} argument, C{fetchBodyStructure} can
        also issue a I{UID FETCH BODYSTRUCTURE} command.
        """
        return self.test_fetchBodyStructure(1)

    def test_fetchBodyStructureMultipart(self, uid=0):
        """
        L{IMAP4Client.fetchBodyStructure} can also parse the response to a
        I{FETCH BODYSTRUCTURE} command for a multipart message.
        """
        self.function = self.client.fetchBodyStructure
        self.messages = "3:9,10:*"
        innerMessage = FakeyMessage(
            {
                "content-type": 'text/plain; name=thing; key="value"',
                "content-id": "this-is-the-content-id",
                "content-description": "describing-the-content-goes-here!",
                "content-transfer-encoding": "8BIT",
                "content-language": "fr",
                "content-md5": "123456abcdef",
                "content-disposition": "inline",
                "content-location": "outer space",
            },
            (),
            b"",
            b"Body\nText\nGoes\nHere\n",
            919293,
            None,
        )
        self.msgObjs = [
            FakeyMessage(
                {
                    "content-type": 'multipart/mixed; boundary="xyz"',
                    "content-language": "en",
                    "content-location": "nearby",
                },
                (),
                b"",
                b"",
                919293,
                [innerMessage],
            )
        ]
        self.expected = {
            0: {
                "BODYSTRUCTURE": [
                    [
                        "text",
                        "plain",
                        ["key", "value", "name", "thing"],
                        "this-is-the-content-id",
                        "describing-the-content-goes-here!",
                        "8BIT",
                        "20",
                        "4",
                        "123456abcdef",
                        ["inline", None],
                        "fr",
                        "outer space",
                    ],
                    "mixed",
                    ["boundary", "xyz"],
                    None,
                    "en",
                    "nearby",
                ]
            }
        }
        return self._fetchWork(uid)

    def testFetchSimplifiedBody(self, uid=0):
        self.function = self.client.fetchSimplifiedBody
        self.messages = "21"
        self.msgObjs = [
            FakeyMessage(
                {},
                (),
                b"",
                b"Yea whatever",
                91825,
                [
                    FakeyMessage(
                        {"content-type": "image/jpg"},
                        (),
                        b"",
                        b"Body Body Body",
                        None,
                        None,
                    )
                ],
            )
        ]
        self.expected = {0: {"BODY": [None, None, None, None, None, None, "12"]}}

        return self._fetchWork(uid)

    def testFetchSimplifiedBodyUID(self):
        return self.testFetchSimplifiedBody(1)

    def testFetchSimplifiedBodyText(self, uid=0):
        self.function = self.client.fetchSimplifiedBody
        self.messages = "21"
        self.msgObjs = [
            FakeyMessage(
                {"content-type": "text/plain"}, (), b"", b"Yea whatever", 91825, None
            )
        ]
        self.expected = {
            0: {"BODY": ["text", "plain", None, None, None, None, "12", "1"]}
        }

        return self._fetchWork(uid)

    def testFetchSimplifiedBodyTextUID(self):
        return self.testFetchSimplifiedBodyText(1)

    def testFetchSimplifiedBodyRFC822(self, uid=0):
        self.function = self.client.fetchSimplifiedBody
        self.messages = "21"
        self.msgObjs = [
            FakeyMessage(
                {"content-type": "message/rfc822"},
                (),
                b"",
                b"Yea whatever",
                91825,
                [
                    FakeyMessage(
                        {"content-type": "image/jpg"},
                        (),
                        "",
                        b"Body Body Body",
                        None,
                        None,
                    )
                ],
            )
        ]
        self.expected = {
            0: {
                "BODY": [
                    "message",
                    "rfc822",
                    None,
                    None,
                    None,
                    None,
                    "12",
                    [
                        None,
                        None,
                        [[None, None, None]],
                        [[None, None, None]],
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ],
                    ["image", "jpg", None, None, None, None, "14"],
                    "1",
                ]
            }
        }

        return self._fetchWork(uid)

    def testFetchSimplifiedBodyRFC822UID(self):
        return self.testFetchSimplifiedBodyRFC822(1)

    def test_fetchSimplifiedBodyMultipart(self):
        """
        L{IMAP4Client.fetchSimplifiedBody} returns a dictionary mapping message
        sequence numbers to fetch responses for the corresponding messages.  In
        particular, for a multipart message, the value in the dictionary maps
        the string C{"BODY"} to a list giving the body structure information for
        that message, in the form of a list of subpart body structure
        information followed by the subtype of the message (eg C{"alternative"}
        for a I{multipart/alternative} message).  This structure is self-similar
        in the case where a subpart is itself multipart.
        """
        self.function = self.client.fetchSimplifiedBody
        self.messages = "21"

        # A couple non-multipart messages to use as the inner-most payload
        singles = [
            FakeyMessage(
                {"content-type": "text/plain"}, (), b"date", b"Stuff", 54321, None
            ),
            FakeyMessage(
                {"content-type": "text/html"}, (), b"date", b"Things", 32415, None
            ),
        ]

        # A multipart/alternative message containing the above non-multipart
        # messages.  This will be the payload of the outer-most message.
        alternative = FakeyMessage(
            {"content-type": "multipart/alternative"},
            (),
            b"",
            b"Irrelevant",
            12345,
            singles,
        )

        # The outer-most message, also with a multipart type, containing just
        # the single middle message.
        mixed = FakeyMessage(
            # The message is multipart/mixed
            {"content-type": "multipart/mixed"},
            (),
            b"",
            b"RootOf",
            98765,
            [alternative],
        )

        self.msgObjs = [mixed]

        self.expected = {
            0: {
                "BODY": [
                    [
                        ["text", "plain", None, None, None, None, "5", "1"],
                        ["text", "html", None, None, None, None, "6", "1"],
                        "alternative",
                    ],
                    "mixed",
                ]
            }
        }

        return self._fetchWork(False)

    def testFetchMessage(self, uid=0):
        self.function = self.client.fetchMessage
        self.messages = "1,3,7,10101"
        self.msgObjs = [
            FakeyMessage({"Header": "Value"}, (), b"", b"BODY TEXT\r\n", 91, None),
        ]
        self.expected = {0: {"RFC822": "Header: Value\r\n\r\nBODY TEXT\r\n"}}
        return self._fetchWork(uid)

    def testFetchMessageUID(self):
        return self.testFetchMessage(1)

    def testFetchHeaders(self, uid=0):
        self.function = self.client.fetchHeaders
        self.messages = "9,6,2"
        self.msgObjs = [
            FakeyMessage({"H1": "V1", "H2": "V2"}, (), b"", b"", 99, None),
        ]

        headers = nativeString(imap4._formatHeaders({"H1": "V1", "H2": "V2"}))

        self.expected = {
            0: {"RFC822.HEADER": headers},
        }
        return self._fetchWork(uid)

    def testFetchHeadersUID(self):
        return self.testFetchHeaders(1)

    def testFetchBody(self, uid=0):
        self.function = self.client.fetchBody
        self.messages = "1,2,3,4,5,6,7"
        self.msgObjs = [
            FakeyMessage({"Header": "Value"}, (), "", b"Body goes here\r\n", 171, None),
        ]
        self.expected = {
            0: {"RFC822.TEXT": "Body goes here\r\n"},
        }
        return self._fetchWork(uid)

    def testFetchBodyUID(self):
        return self.testFetchBody(1)

    def testFetchBodyParts(self):
        """
        Test the server's handling of requests for specific body sections.
        """
        self.function = self.client.fetchSpecific
        self.messages = "1"
        outerBody = ""
        innerBody1 = b"Contained body message text.  Squarge."
        innerBody2 = b"Secondary <i>message</i> text of squarge body."
        headers = OrderedDict()
        headers["from"] = "sender@host"
        headers["to"] = "recipient@domain"
        headers["subject"] = "booga booga boo"
        headers["content-type"] = 'multipart/alternative; boundary="xyz"'
        innerHeaders = OrderedDict()
        innerHeaders["subject"] = "this is subject text"
        innerHeaders["content-type"] = "text/plain"
        innerHeaders2 = OrderedDict()
        innerHeaders2["subject"] = "<b>this is subject</b>"
        innerHeaders2["content-type"] = "text/html"
        self.msgObjs = [
            FakeyMessage(
                headers,
                (),
                None,
                outerBody,
                123,
                [
                    FakeyMessage(innerHeaders, (), None, innerBody1, None, None),
                    FakeyMessage(innerHeaders2, (), None, innerBody2, None, None),
                ],
            )
        ]
        self.expected = {0: [["BODY", ["1"], "Contained body message text.  Squarge."]]}

        def result(R):
            self.result = R

        self.connected.addCallback(
            lambda _: self.function(self.messages, headerNumber=1)
        )
        self.connected.addCallback(result)
        self.connected.addCallback(self._cbStopClient)
        self.connected.addErrback(self._ebGeneral)

        d = loopback.loopbackTCP(self.server, self.client, noisy=False)
        d.addCallback(lambda ign: self.assertEqual(self.result, self.expected))
        return d

    def test_fetchBodyPartOfNonMultipart(self):
        """
        Single-part messages have an implicit first part which clients
        should be able to retrieve explicitly.  Test that a client
        requesting part 1 of a text/plain message receives the body of the
        text/plain part.
        """
        self.function = self.client.fetchSpecific
        self.messages = "1"
        parts = [1]
        outerBody = b"DA body"
        headers = OrderedDict()
        headers["from"] = "sender@host"
        headers["to"] = "recipient@domain"
        headers["subject"] = "booga booga boo"
        headers["content-type"] = "text/plain"
        self.msgObjs = [FakeyMessage(headers, (), None, outerBody, 123, None)]

        self.expected = {0: [["BODY", ["1"], "DA body"]]}

        def result(R):
            self.result = R

        self.connected.addCallback(
            lambda _: self.function(self.messages, headerNumber=parts)
        )
        self.connected.addCallback(result)
        self.connected.addCallback(self._cbStopClient)
        self.connected.addErrback(self._ebGeneral)

        d = loopback.loopbackTCP(self.server, self.client, noisy=False)
        d.addCallback(lambda ign: self.assertEqual(self.result, self.expected))
        return d

    def testFetchSize(self, uid=0):
        self.function = self.client.fetchSize
        self.messages = "1:100,2:*"
        self.msgObjs = [
            FakeyMessage({}, (), b"", b"x" * 20, 123, None),
        ]
        self.expected = {
            0: {"RFC822.SIZE": "20"},
        }
        return self._fetchWork(uid)

    def testFetchSizeUID(self):
        return self.testFetchSize(1)

    def testFetchFull(self, uid=0):
        self.function = self.client.fetchFull
        self.messages = "1,3"
        self.msgObjs = [
            FakeyMessage(
                {},
                ("\\XYZ", "\\YZX", "Abc"),
                b"Sun, 25 Jul 2010 06:20:30 -0400 (EDT)",
                b"xyz" * 2,
                654,
                None,
            ),
            FakeyMessage(
                {},
                ("\\One", "\\Two", "Three"),
                b"Mon, 14 Apr 2003 19:43:44 -0400",
                b"abc" * 4,
                555,
                None,
            ),
        ]
        self.expected = {
            0: {
                "FLAGS": ["\\XYZ", "\\YZX", "Abc"],
                "INTERNALDATE": "25-Jul-2010 06:20:30 -0400",
                "RFC822.SIZE": "6",
                "ENVELOPE": [
                    None,
                    None,
                    [[None, None, None]],
                    [[None, None, None]],
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ],
                "BODY": [None, None, None, None, None, None, "6"],
            },
            1: {
                "FLAGS": ["\\One", "\\Two", "Three"],
                "INTERNALDATE": "14-Apr-2003 19:43:44 -0400",
                "RFC822.SIZE": "12",
                "ENVELOPE": [
                    None,
                    None,
                    [[None, None, None]],
                    [[None, None, None]],
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ],
                "BODY": [None, None, None, None, None, None, "12"],
            },
        }
        return self._fetchWork(uid)

    def testFetchFullUID(self):
        return self.testFetchFull(1)

    def testFetchAll(self, uid=0):
        self.function = self.client.fetchAll
        self.messages = "1,2:3"
        self.msgObjs = [
            FakeyMessage(
                {}, (), b"Mon, 14 Apr 2003 19:43:44 +0400", b"Lalala", 10101, None
            ),
            FakeyMessage(
                {}, (), b"Tue, 15 Apr 2003 19:43:44 +0200", b"Alalal", 20202, None
            ),
        ]
        self.expected = {
            0: {
                "ENVELOPE": [
                    None,
                    None,
                    [[None, None, None]],
                    [[None, None, None]],
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ],
                "RFC822.SIZE": "6",
                "INTERNALDATE": "14-Apr-2003 19:43:44 +0400",
                "FLAGS": [],
            },
            1: {
                "ENVELOPE": [
                    None,
                    None,
                    [[None, None, None]],
                    [[None, None, None]],
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ],
                "RFC822.SIZE": "6",
                "INTERNALDATE": "15-Apr-2003 19:43:44 +0200",
                "FLAGS": [],
            },
        }
        return self._fetchWork(uid)

    def testFetchAllUID(self):
        return self.testFetchAll(1)

    def testFetchFast(self, uid=0):
        self.function = self.client.fetchFast
        self.messages = "1"
        self.msgObjs = [
            FakeyMessage({}, ("\\X",), b"19 Mar 2003 19:22:21 -0500", b"", 9, None),
        ]
        self.expected = {
            0: {
                "FLAGS": ["\\X"],
                "INTERNALDATE": "19-Mar-2003 19:22:21 -0500",
                "RFC822.SIZE": "0",
            },
        }
        return self._fetchWork(uid)

    def testFetchFastUID(self):
        return self.testFetchFast(1)


class DefaultSearchTests(IMAP4HelperMixin, TestCase):
    """
    Test the behavior of the server's SEARCH implementation, particularly in
    the face of unhandled search terms.
    """

    def setUp(self):
        self.server = imap4.IMAP4Server()
        self.server.state = "select"
        self.server.mbox = self
        self.connected = defer.Deferred()
        self.client = SimpleClient(self.connected)
        self.msgObjs = [
            FakeyMessage({}, (), b"", b"", 999, None),
            FakeyMessage({}, (), b"", b"", 10101, None),
            FakeyMessage({}, (), b"", b"", 12345, None),
            FakeyMessage({}, (), b"", b"", 20001, None),
            FakeyMessage({}, (), b"", b"", 20002, None),
        ]

    def fetch(self, messages, uid):
        """
        Pretend to be a mailbox and let C{self.server} lookup messages on me.
        """
        return list(zip(range(1, len(self.msgObjs) + 1), self.msgObjs))

    def _messageSetSearchTest(self, queryTerms, expectedMessages):
        """
        Issue a search with given query and verify that the returned messages
        match the given expected messages.

        @param queryTerms: A string giving the search query.
        @param expectedMessages: A list of the message sequence numbers
            expected as the result of the search.
        @return: A L{Deferred} which fires when the test is complete.
        """

        def search():
            return self.client.search(queryTerms)

        d = self.connected.addCallback(strip(search))

        def searched(results):
            self.assertEqual(results, expectedMessages)

        d.addCallback(searched)
        d.addCallback(self._cbStopClient)
        d.addErrback(self._ebGeneral)
        self.loopback()
        return d

    def test_searchMessageSet(self):
        """
        Test that a search which starts with a message set properly limits
        the search results to messages in that set.
        """
        return self._messageSetSearchTest("1", [1])

    def test_searchMessageSetWithStar(self):
        """
        If the search filter ends with a star, all the message from the
        starting point are returned.
        """
        return self._messageSetSearchTest("2:*", [2, 3, 4, 5])

    def test_searchMessageSetWithStarFirst(self):
        """
        If the search filter starts with a star, the result should be identical
        with if the filter would end with a star.
        """
        return self._messageSetSearchTest("*:2", [2, 3, 4, 5])

    def test_searchMessageSetUIDWithStar(self):
        """
        If the search filter ends with a star, all the message from the
        starting point are returned (also for the SEARCH UID case).
        """
        return self._messageSetSearchTest("UID 10000:*", [2, 3, 4, 5])

    def test_searchMessageSetUIDWithStarFirst(self):
        """
        If the search filter starts with a star, the result should be identical
        with if the filter would end with a star (also for the SEARCH UID case).
        """
        return self._messageSetSearchTest("UID *:10000", [2, 3, 4, 5])

    def test_searchMessageSetUIDWithStarAndHighStart(self):
        """
        A search filter of 1234:* should include the UID of the last message in
        the mailbox, even if its UID is less than 1234.
        """
        # in our fake mbox the highest message UID is 20002
        return self._messageSetSearchTest("UID 30000:*", [5])

    def test_searchMessageSetWithList(self):
        """
        If the search filter contains nesting terms, one of which includes a
        message sequence set with a wildcard, IT ALL WORKS GOOD.
        """
        # 6 is bigger than the biggest message sequence number, but that's
        # okay, because N:* includes the biggest message sequence number even
        # if N is bigger than that (read the rfc nub).
        return self._messageSetSearchTest("(6:*)", [5])

    def test_searchOr(self):
        """
        If the search filter contains an I{OR} term, all messages
        which match either subexpression are returned.
        """
        return self._messageSetSearchTest("OR 1 2", [1, 2])

    def test_searchOrMessageSet(self):
        """
        If the search filter contains an I{OR} term with a
        subexpression which includes a message sequence set wildcard,
        all messages in that set are considered for inclusion in the
        results.
        """
        return self._messageSetSearchTest("OR 2:* 2:*", [2, 3, 4, 5])

    def test_searchNot(self):
        """
        If the search filter contains a I{NOT} term, all messages
        which do not match the subexpression are returned.
        """
        return self._messageSetSearchTest("NOT 3", [1, 2, 4, 5])

    def test_searchNotMessageSet(self):
        """
        If the search filter contains a I{NOT} term with a
        subexpression which includes a message sequence set wildcard,
        no messages in that set are considered for inclusion in the
        result.
        """
        return self._messageSetSearchTest("NOT 2:*", [1])

    def test_searchAndMessageSet(self):
        """
        If the search filter contains multiple terms implicitly
        conjoined with a message sequence set wildcard, only the
        intersection of the results of each term are returned.
        """
        return self._messageSetSearchTest("2:* 3", [3])

    def test_searchInvalidCriteria(self):
        """
        If the search criteria is not a valid key, a NO result is returned to
        the client (resulting in an error callback), and an IllegalQueryError is
        logged on the server side.
        """
        queryTerms = "FOO"

        def search():
            return self.client.search(queryTerms)

        d = self.connected.addCallback(strip(search))
        d = self.assertFailure(d, imap4.IMAP4Exception)

        def errorReceived(results):
            """
            Verify that the server logs an IllegalQueryError and the
            client raises an IMAP4Exception with 'Search failed:...'
            """
            self.client.transport.loseConnection()
            self.server.transport.loseConnection()

            # Check what the server logs
            errors = self.flushLoggedErrors(imap4.IllegalQueryError)
            self.assertEqual(len(errors), 1)

            # Verify exception given to client has the correct message
            self.assertEqual(
                str(b"SEARCH failed: Invalid search command FOO"),
                str(results),
            )

        d.addCallback(errorReceived)
        d.addErrback(self._ebGeneral)
        self.loopback()
        return d


@implementer(imap4.ISearchableMailbox)
class FetchSearchStoreTests(TestCase, IMAP4HelperMixin):
    def setUp(self):
        self.expected = self.result = None
        self.server_received_query = None
        self.server_received_uid = None
        self.server_received_parts = None
        self.server_received_messages = None

        self.server = imap4.IMAP4Server()
        self.server.state = "select"
        self.server.mbox = self
        self.connected = defer.Deferred()
        self.client = SimpleClient(self.connected)

    def search(self, query, uid):
        # Look for a specific bad query, so we can verify we handle it properly
        if query == [b"FOO"]:
            raise imap4.IllegalQueryError("FOO is not a valid search criteria")

        self.server_received_query = query
        self.server_received_uid = uid
        return self.expected

    def addListener(self, *a, **kw):
        pass

    removeListener = addListener

    def _searchWork(self, uid):
        def search():
            return self.client.search(self.query, uid=uid)

        def result(R):
            self.result = R

        self.connected.addCallback(strip(search)).addCallback(result).addCallback(
            self._cbStopClient
        ).addErrback(self._ebGeneral)

        def check(ignored):
            # Ensure no short-circuiting weirdness is going on
            self.assertFalse(self.result is self.expected)

            self.assertEqual(self.result, self.expected)
            self.assertEqual(self.uid, self.server_received_uid)
            self.assertEqual(
                # Queries should be decoded as ASCII unless a charset
                # identifier is provided.  See #9201.
                imap4.parseNestedParens(self.query.encode("charmap")),
                self.server_received_query,
            )

        d = loopback.loopbackTCP(self.server, self.client, noisy=False)
        d.addCallback(check)
        return d

    def testSearch(self):
        self.query = imap4.Or(
            imap4.Query(header=("subject", "substring")),
            imap4.Query(larger=1024, smaller=4096),
        )
        self.expected = [1, 4, 5, 7]
        self.uid = 0
        return self._searchWork(0)

    def testUIDSearch(self):
        self.query = imap4.Or(
            imap4.Query(header=("subject", "substring")),
            imap4.Query(larger=1024, smaller=4096),
        )
        self.uid = 1
        self.expected = [1, 2, 3]
        return self._searchWork(1)

    def getUID(self, msg):
        try:
            return self.expected[msg]["UID"]
        except (TypeError, IndexError):
            return self.expected[msg - 1]
        except KeyError:
            return 42

    def fetch(self, messages, uid):
        self.server_received_uid = uid
        self.server_received_messages = str(messages)
        return self.expected

    def _fetchWork(self, fetch):
        def result(R):
            self.result = R

        self.connected.addCallback(strip(fetch)).addCallback(result).addCallback(
            self._cbStopClient
        ).addErrback(self._ebGeneral)

        def check(ignored):
            # Ensure no short-circuiting weirdness is going on
            self.assertFalse(self.result is self.expected)

            self.parts and self.parts.sort()
            self.server_received_parts and self.server_received_parts.sort()

            if self.uid:
                for (k, v) in self.expected.items():
                    v["UID"] = str(k)

            self.assertEqual(self.result, self.expected)
            self.assertEqual(self.uid, self.server_received_uid)
            self.assertEqual(self.parts, self.server_received_parts)
            self.assertEqual(
                imap4.parseIdList(self.messages),
                imap4.parseIdList(self.server_received_messages),
            )

        d = loopback.loopbackTCP(self.server, self.client, noisy=False)
        d.addCallback(check)
        return d

    def test_invalidTerm(self):
        """
        If, as part of a search, an ISearchableMailbox raises an
        IllegalQueryError (e.g. due to invalid search criteria), client sees a
        failure response, and an IllegalQueryError is logged on the server.
        """
        query = "FOO"

        def search():
            return self.client.search(query)

        d = self.connected.addCallback(strip(search))
        d = self.assertFailure(d, imap4.IMAP4Exception)

        def errorReceived(results):
            """
            Verify that the server logs an IllegalQueryError and the
            client raises an IMAP4Exception with 'Search failed:...'
            """
            self.client.transport.loseConnection()
            self.server.transport.loseConnection()

            # Check what the server logs
            errors = self.flushLoggedErrors(imap4.IllegalQueryError)
            self.assertEqual(len(errors), 1)

            # Verify exception given to client has the correct message
            self.assertEqual(
                str(b"SEARCH failed: FOO is not a valid search criteria"), str(results)
            )

        d.addCallback(errorReceived)
        d.addErrback(self._ebGeneral)
        self.loopback()
        return d


class FakeMailbox:
    def __init__(self):
        self.args = []

    def addMessage(self, body, flags, date):
        self.args.append((body, flags, date))
        return defer.succeed(None)


@implementer(imap4.IMessageFile)
class FeaturefulMessage:
    def getFlags(self):
        return "flags"

    def getInternalDate(self):
        return "internaldate"

    def open(self):
        return BytesIO(b"open")


@implementer(imap4.IMessageCopier)
class MessageCopierMailbox:
    def __init__(self):
        self.msgs = []

    def copy(self, msg):
        self.msgs.append(msg)
        return len(self.msgs)


class CopyWorkerTests(TestCase):
    def testFeaturefulMessage(self):
        s = imap4.IMAP4Server()

        # Yes.  I am grabbing this uber-non-public method to test it.
        # It is complex.  It needs to be tested directly!
        # Perhaps it should be refactored, simplified, or split up into
        # not-so-private components, but that is a task for another day.

        # Ha ha! Addendum!  Soon it will be split up, and this test will
        # be re-written to just use the default adapter for IMailbox to
        # IMessageCopier and call .copy on that adapter.
        f = s._IMAP4Server__cbCopy

        m = FakeMailbox()
        d = f([(i, FeaturefulMessage()) for i in range(1, 11)], "tag", m)

        def cbCopy(results):
            for a in m.args:
                self.assertEqual(a[0].read(), b"open")
                self.assertEqual(a[1], "flags")
                self.assertEqual(a[2], "internaldate")

            for (status, result) in results:
                self.assertTrue(status)
                self.assertEqual(result, None)

        return d.addCallback(cbCopy)

    def testUnfeaturefulMessage(self):
        s = imap4.IMAP4Server()

        # See above comment
        f = s._IMAP4Server__cbCopy

        m = FakeMailbox()
        msgs = [
            FakeyMessage(
                {"Header-Counter": str(i)}, (), b"Date", b"Body %d" % (i,), i + 10, None
            )
            for i in range(1, 11)
        ]
        d = f([im for im in zip(range(1, 11), msgs)], "tag", m)

        def cbCopy(results):
            seen = []
            for a in m.args:
                seen.append(a[0].read())
                self.assertEqual(a[1], ())
                self.assertEqual(a[2], b"Date")

            seen.sort()
            exp = sorted(
                b"Header-Counter: %d\r\n\r\nBody %d" % (i, i) for i in range(1, 11)
            )
            self.assertEqual(seen, exp)

            for (status, result) in results:
                self.assertTrue(status)
                self.assertEqual(result, None)

        return d.addCallback(cbCopy)

    def testMessageCopier(self):
        s = imap4.IMAP4Server()

        # See above comment
        f = s._IMAP4Server__cbCopy

        m = MessageCopierMailbox()
        msgs = [object() for i in range(1, 11)]
        d = f([im for im in zip(range(1, 11), msgs)], b"tag", m)

        def cbCopy(results):
            self.assertEqual(results, list(zip([1] * 10, range(1, 11))))
            for (orig, new) in zip(msgs, m.msgs):
                self.assertIdentical(orig, new)

        return d.addCallback(cbCopy)


@skipIf(not ClientTLSContext, "OpenSSL not present")
@skipIf(not interfaces.IReactorSSL(reactor, None), "Reactor doesn't support SSL")
class TLSTests(IMAP4HelperMixin, TestCase):
    serverCTX = None
    clientCTX = None
    if ServerTLSContext:
        serverCTX = ServerTLSContext()
    if ClientTLSContext:
        clientCTX = ClientTLSContext()

    def loopback(self):
        return loopback.loopbackTCP(self.server, self.client, noisy=False)

    def testAPileOfThings(self):
        SimpleServer.theAccount.addMailbox(b"inbox")
        called = []

        def login():
            called.append(None)
            return self.client.login(b"testuser", b"password-test")

        def list():
            called.append(None)
            return self.client.list(b"inbox", b"%")

        def status():
            called.append(None)
            return self.client.status(b"inbox", "UIDNEXT")

        def examine():
            called.append(None)
            return self.client.examine(b"inbox")

        def logout():
            called.append(None)
            return self.client.logout()

        self.client.requireTransportSecurity = True

        methods = [login, list, status, examine, logout]
        for method in methods:
            self.connected.addCallback(strip(method))

        self.connected.addCallbacks(self._cbStopClient, self._ebGeneral)

        def check(ignored):
            self.assertEqual(self.server.startedTLS, True)
            self.assertEqual(self.client.startedTLS, True)
            self.assertEqual(len(called), len(methods))

        d = self.loopback()
        d.addCallback(check)
        return d

    def testLoginLogin(self):
        self.server.checker.addUser(b"testuser", b"password-test")
        success = []
        self.client.registerAuthenticator(imap4.LOGINAuthenticator(b"testuser"))
        self.connected.addCallback(
            lambda _: self.client.authenticate(b"password-test")
        ).addCallback(lambda _: self.client.logout()).addCallback(
            success.append
        ).addCallback(
            self._cbStopClient
        ).addErrback(
            self._ebGeneral
        )

        d = self.loopback()
        d.addCallback(lambda x: self.assertEqual(len(success), 1))
        return d

    def startTLSAndAssertSession(self):
        """
        Begin a C{STARTTLS} sequence and assert that it results in a
        TLS session.

        @return: A L{Deferred} that fires when the underlying
            connection between the client and server has been terminated.
        """
        success = []
        self.connected.addCallback(strip(self.client.startTLS))

        def checkSecure(ignored):
            self.assertTrue(interfaces.ISSLTransport.providedBy(self.client.transport))

        self.connected.addCallback(checkSecure)
        self.connected.addCallback(success.append)

        d = self.loopback()
        d.addCallback(lambda x: self.assertTrue(success))
        return defer.gatherResults([d, self.connected])

    def test_startTLS(self):
        """
        L{IMAP4Client.startTLS} triggers TLS negotiation and returns a
        L{Deferred} which fires after the client's transport is using
        encryption.
        """
        disconnected = self.startTLSAndAssertSession()
        self.connected.addCallback(self._cbStopClient)
        self.connected.addErrback(self._ebGeneral)
        return disconnected

    def test_startTLSDefault(self) -> Deferred[object]:
        """
        L{IMAPClient.startTLS} supplies a default TLS context if none is
        supplied.
        """
        self.assertIsNotNone(self.client.context)
        self.client.context = None
        disconnected: Deferred[object] = self.startTLSAndAssertSession()
        self.connected.addCallback(self._cbStopClient)
        self.connected.addErrback(self._ebGeneral)
        return disconnected

    def test_doubleSTARTTLS(self):
        """
        A server that receives a second C{STARTTLS} sends a C{NO}
        response.
        """

        class DoubleSTARTTLSClient(SimpleClient):
            def startTLS(self):
                if not self.startedTLS:
                    return SimpleClient.startTLS(self)

                return self.sendCommand(imap4.Command(b"STARTTLS"))

        self.client = DoubleSTARTTLSClient(
            self.connected, contextFactory=self.clientCTX
        )

        disconnected = self.startTLSAndAssertSession()

        self.connected.addCallback(strip(self.client.startTLS))
        self.connected.addErrback(
            self.assertClientFailureMessage, b"TLS already negotiated"
        )

        self.connected.addCallback(self._cbStopClient)
        self.connected.addErrback(self._ebGeneral)

        return disconnected

    def test_startTLSWithExistingChallengers(self):
        """
        Starting a TLS negotiation with an L{IMAP4Server} that already
        has C{LOGIN} and C{PLAIN} L{IChallengeResponse} factories uses
        those factories.
        """
        self.server.challengers = {
            b"LOGIN": imap4.LOGINCredentials,
            b"PLAIN": imap4.PLAINCredentials,
        }

        @defer.inlineCallbacks
        def assertLOGINandPLAIN():
            capabilities = yield self.client.getCapabilities()
            self.assertIn(b"AUTH", capabilities)
            self.assertIn(b"LOGIN", capabilities[b"AUTH"])
            self.assertIn(b"PLAIN", capabilities[b"AUTH"])

        self.connected.addCallback(strip(assertLOGINandPLAIN))

        disconnected = self.startTLSAndAssertSession()

        self.connected.addCallback(strip(assertLOGINandPLAIN))

        self.connected.addCallback(self._cbStopClient)
        self.connected.addErrback(self._ebGeneral)

        return disconnected

    def test_loginBeforeSTARTTLS(self):
        """
        A client that attempts to log in before issuing the
        C{STARTTLS} command receives a C{NO} response.
        """
        # Prevent the client from issuing STARTTLS.
        self.client.startTLS = lambda: defer.succeed(
            ([], "OK Begin TLS negotiation now")
        )
        self.connected.addCallback(
            lambda _: self.client.login(b"wrong", b"time"),
        )

        self.connected.addErrback(
            self.assertClientFailureMessage,
            b"LOGIN is disabled before STARTTLS",
        )

        self.connected.addCallback(self._cbStopClient)
        self.connected.addErrback(self._ebGeneral)

        return defer.gatherResults([self.loopback(), self.connected])

    def testFailedStartTLS(self):
        failures = []

        def breakServerTLS(ign):
            self.server.canStartTLS = False

        self.connected.addCallback(breakServerTLS)
        self.connected.addCallback(lambda ign: self.client.startTLS())
        self.connected.addErrback(
            lambda err: failures.append(err.trap(imap4.IMAP4Exception))
        )
        self.connected.addCallback(self._cbStopClient)
        self.connected.addErrback(self._ebGeneral)

        def check(ignored):
            self.assertTrue(failures)
            self.assertIdentical(failures[0], imap4.IMAP4Exception)

        return self.loopback().addCallback(check)


class SlowMailbox(SimpleMailbox):
    howSlow = 2
    callLater = None
    fetchDeferred = None

    # Not a very nice implementation of fetch(), but it'll
    # do for the purposes of testing.
    def fetch(self, messages, uid):
        d = defer.Deferred()
        self.callLater(self.howSlow, d.callback, ())
        self.fetchDeferred.callback(None)
        return d


class TimeoutTests(IMAP4HelperMixin, TestCase):
    def test_serverTimeout(self):
        """
        The *client* has a timeout mechanism which will close connections that
        are inactive for a period.
        """
        c = Clock()
        self.server.timeoutTest = True
        self.client.timeout = 5  # seconds
        self.client.callLater = c.callLater
        self.selectedArgs = None

        def login():
            d = self.client.login(b"testuser", b"password-test")
            c.advance(5)
            d.addErrback(timedOut)
            return d

        def timedOut(failure):
            self._cbStopClient(None)
            failure.trap(error.TimeoutError)

        d = self.connected.addCallback(strip(login))
        d.addErrback(self._ebGeneral)
        return defer.gatherResults([d, self.loopback()])

    def test_serverTimesOut(self):
        """
        The server times out a connection.
        """
        c = Clock()
        self.server.callLater = c.callLater

        def login():
            return self.client.login(b"testuser", b"password-test")

        def expireTime():
            c.advance(self.server.POSTAUTH_TIMEOUT * 2)

        d = self.connected.addCallback(strip(login))
        d.addCallback(strip(expireTime))

        # The loopback method's Deferred fires the connection is
        # closed, and the server closes the connection as a result of
        # expireTime.
        return defer.gatherResults([d, self.loopback()])

    def test_serverUnselectsMailbox(self):
        """
        The server unsets the selected mailbox when timing out a
        connection.
        """
        self.patch(SimpleServer.theAccount, "mailboxFactory", UncloseableMailbox)
        SimpleServer.theAccount.addMailbox("mailbox-test")
        mbox = SimpleServer.theAccount.mailboxes["MAILBOX-TEST"]
        self.assertFalse(ICloseableMailboxIMAP.providedBy(mbox))

        c = Clock()
        self.server.callLater = c.callLater

        def login():
            return self.client.login(b"testuser", b"password-test")

        def select():
            return self.client.select("mailbox-test")

        def assertSet():
            self.assertIs(mbox, self.server.mbox)

        def expireTime():
            c.advance(self.server.POSTAUTH_TIMEOUT * 2)

        def assertUnset():
            self.assertFalse(self.server.mbox)

        d = self.connected.addCallback(strip(login))
        d.addCallback(strip(select))
        d.addCallback(strip(assertSet))
        d.addCallback(strip(expireTime))
        d.addCallback(strip(assertUnset))

        # The loopback method's Deferred fires the connection is
        # closed, and the server closes the connection as a result of
        # expireTime.
        return defer.gatherResults([d, self.loopback()])

    def test_serverTimesOutAndClosesMailbox(self):
        """
        The server closes the selected, closeable mailbox when timing
        out a connection.
        """
        SimpleServer.theAccount.addMailbox("mailbox-test")
        mbox = SimpleServer.theAccount.mailboxes["MAILBOX-TEST"]
        verifyObject(ICloseableMailboxIMAP, mbox)

        c = Clock()
        self.server.callLater = c.callLater

        def login():
            return self.client.login(b"testuser", b"password-test")

        def select():
            return self.client.select("mailbox-test")

        def assertMailboxOpen():
            self.assertFalse(mbox.closed)

        def expireTime():
            c.advance(self.server.POSTAUTH_TIMEOUT * 2)

        def assertMailboxClosed():
            self.assertTrue(mbox.closed)

        d = self.connected.addCallback(strip(login))
        d.addCallback(strip(select))
        d.addCallback(strip(assertMailboxOpen))
        d.addCallback(strip(expireTime))
        d.addCallback(strip(assertMailboxClosed))

        # The loopback method's Deferred fires the connection is
        # closed, and the server closes the connection as a result of
        # expireTime.
        return defer.gatherResults([d, self.loopback()])

    def test_longFetchDoesntTimeout(self):
        """
        The connection timeout does not take effect during fetches.
        """
        c = Clock()
        SlowMailbox.callLater = c.callLater
        SlowMailbox.fetchDeferred = defer.Deferred()
        self.server.callLater = c.callLater
        SimpleServer.theAccount.mailboxFactory = SlowMailbox
        SimpleServer.theAccount.addMailbox("mailbox-test")

        self.server.setTimeout(1)

        def login():
            return self.client.login(b"testuser", b"password-test")

        def select():
            self.server.setTimeout(1)
            return self.client.select("mailbox-test")

        def fetch():
            return self.client.fetchUID("1:*")

        def stillConnected():
            self.assertNotEqual(self.server.state, "timeout")

        def cbAdvance(ignored):
            for i in range(4):
                c.advance(0.5)

        SlowMailbox.fetchDeferred.addCallback(cbAdvance)

        d1 = self.connected.addCallback(strip(login))
        d1.addCallback(strip(select))
        d1.addCallback(strip(fetch))
        d1.addCallback(strip(stillConnected))
        d1.addCallback(self._cbStopClient)
        d1.addErrback(self._ebGeneral)
        d = defer.gatherResults([d1, self.loopback()])
        return d

    def test_idleClientDoesDisconnect(self):
        """
        The *server* has a timeout mechanism which will close connections that
        are inactive for a period.
        """
        c = Clock()
        # Hook up our server protocol
        transport = StringTransportWithDisconnection()
        transport.protocol = self.server
        self.server.callLater = c.callLater
        self.server.makeConnection(transport)

        # Make sure we can notice when the connection goes away
        lost = []
        connLost = self.server.connectionLost
        self.server.connectionLost = lambda reason: (
            lost.append(None),
            connLost(reason),
        )[1]

        # 2/3rds of the idle timeout elapses...
        c.pump([0.0] + [self.server.timeOut / 3.0] * 2)
        self.assertFalse(lost, lost)

        # Now some more
        c.pump([0.0, self.server.timeOut / 2.0])
        self.assertTrue(lost)


class DisconnectionTests(TestCase):
    def testClientDisconnectFailsDeferreds(self):
        c = imap4.IMAP4Client()
        t = StringTransportWithDisconnection()
        c.makeConnection(t)
        d = self.assertFailure(
            c.login(b"testuser", "example.com"), error.ConnectionDone
        )
        c.connectionLost(error.ConnectionDone("Connection closed"))
        return d


class SynchronousMailbox:
    """
    Trivial, in-memory mailbox implementation which can produce a message
    synchronously.
    """

    def __init__(self, messages):
        self.messages = messages

    def fetch(self, msgset, uid):
        assert not uid, "Cannot handle uid requests."
        for msg in msgset:
            yield msg, self.messages[msg - 1]


class PipeliningTests(TestCase):
    """
    Tests for various aspects of the IMAP4 server's pipelining support.
    """

    messages = [
        FakeyMessage({}, [], b"", b"0", None, None),
        FakeyMessage({}, [], b"", b"1", None, None),
        FakeyMessage({}, [], b"", b"2", None, None),
    ]

    def setUp(self):
        self.iterators = []

        self.transport = StringTransport()
        self.server = imap4.IMAP4Server(None, None, self.iterateInReactor)
        self.server.makeConnection(self.transport)

        mailbox = SynchronousMailbox(self.messages)

        # Skip over authentication and folder selection
        self.server.state = "select"
        self.server.mbox = mailbox

        # Get rid of any greeting junk
        self.transport.clear()

    def iterateInReactor(self, iterator):
        """
        A fake L{imap4.iterateInReactor} that records the iterators it
        receives.

        @param iterator: An iterator.

        @return: A L{Deferred} associated with this iterator.
        """
        d = defer.Deferred()
        self.iterators.append((iterator, d))
        return d

    def flushPending(self, asLongAs=lambda: True):
        """
        Advance pending iterators enqueued with L{iterateInReactor} in
        a round-robin fashion, resuming the transport's producer until
        it has completed.  This ensures bodies are flushed.

        @param asLongAs: (optional) An optional predicate function.
            Flushing iterators continues as long as there are
            iterators and this returns L{True}.
        """
        while self.iterators and asLongAs():
            for e in self.iterators[0][0]:
                while self.transport.producer:
                    self.transport.producer.resumeProducing()
            else:
                self.iterators.pop(0)[1].callback(None)

    def tearDown(self):
        self.server.connectionLost(failure.Failure(error.ConnectionDone()))

    def test_synchronousFetch(self):
        """
        Test that pipelined FETCH commands which can be responded to
        synchronously are responded to correctly.
        """
        # Here's some pipelined stuff
        self.server.dataReceived(
            b"01 FETCH 1 BODY[]\r\n" b"02 FETCH 2 BODY[]\r\n" b"03 FETCH 3 BODY[]\r\n"
        )

        self.flushPending()

        self.assertEqual(
            self.transport.value(),
            b"".join(
                [
                    b"* 1 FETCH (BODY[] )\r\n",
                    networkString(
                        "01 OK FETCH completed\r\n{5}\r\n\r\n\r\n%s"
                        % (nativeString(self.messages[0].getBodyFile().read()),)
                    ),
                    b"* 2 FETCH (BODY[] )\r\n",
                    networkString(
                        "02 OK FETCH completed\r\n{5}\r\n\r\n\r\n%s"
                        % (nativeString(self.messages[1].getBodyFile().read()),)
                    ),
                    b"* 3 FETCH (BODY[] )\r\n",
                    networkString(
                        "03 OK FETCH completed\r\n{5}\r\n\r\n\r\n%s"
                        % (nativeString(self.messages[2].getBodyFile().read()),)
                    ),
                ]
            ),
        )

    def test_bufferedServerStatus(self):
        """
        When a server status change occurs during an ongoing FETCH
        command, the server status is buffered until the FETCH
        completes.
        """
        self.server.dataReceived(b"01 FETCH 1,2 BODY[]\r\n")

        # Two iterations yields the untagged response and the first
        # fetched message's body
        twice = functools.partial(next, iter([True, True, False]))
        self.flushPending(asLongAs=twice)

        self.assertEqual(
            self.transport.value(),
            b"".join(
                [
                    # The untagged response...
                    b"* 1 FETCH (BODY[] )\r\n",
                    # ...and its body
                    networkString(
                        "{5}\r\n\r\n\r\n%s"
                        % (nativeString(self.messages[0].getBodyFile().read()),)
                    ),
                ]
            ),
        )

        self.transport.clear()

        # A server status change...
        self.server.modeChanged(writeable=True)

        # ...remains buffered...
        self.assertFalse(self.transport.value())

        self.flushPending()

        self.assertEqual(
            self.transport.value(),
            b"".join(
                [
                    # The untagged response...
                    b"* 2 FETCH (BODY[] )\r\n",
                    # ...the status change...
                    b"* [READ-WRITE]\r\n",
                    # ...and the completion status and final message's body
                    networkString(
                        "01 OK FETCH completed\r\n{5}\r\n\r\n\r\n%s"
                        % (nativeString(self.messages[1].getBodyFile().read()),)
                    ),
                ]
            ),
        )


class IMAP4ServerFetchTests(TestCase):
    """
    This test case is for the FETCH tests that require
    a C{StringTransport}.
    """

    def setUp(self):
        self.transport = StringTransport()
        self.server = imap4.IMAP4Server()
        self.server.state = "select"
        self.server.makeConnection(self.transport)

    def test_fetchWithPartialValidArgument(self):
        """
        If by any chance, extra bytes got appended at the end of a valid
        FETCH arguments, the client should get a BAD - arguments invalid
        response.

        See U{RFC 3501<http://tools.ietf.org/html/rfc3501#section-6.4.5>},
        section 6.4.5,
        """
        # We need to clear out the welcome message.
        self.transport.clear()
        # Let's send out the faulty command.
        self.server.dataReceived(b"0001 FETCH 1 FULLL\r\n")
        expected = b"0001 BAD Illegal syntax: Invalid Argument\r\n"
        self.assertEqual(self.transport.value(), expected)
        self.transport.clear()
        self.server.connectionLost(error.ConnectionDone("Connection closed"))


class LiteralTestsMixin:
    """
    Shared tests for literal classes.

    @ivar literalFactory: A callable that returns instances of the
        literal under test.
    """

    def setUp(self):
        """
        Shared setup.
        """
        self.deferred = defer.Deferred()

    def test_partialWrite(self):
        """
        The literal returns L{None} when given less data than the
        literal requires.
        """
        literal = self.literalFactory(1024, self.deferred)
        self.assertIs(None, literal.write(b"incomplete"))
        self.assertNoResult(self.deferred)

    def test_exactWrite(self):
        """
        The literal returns an empty L{bytes} instance when given
        exactly the data the literal requires.
        """
        data = b"complete"
        literal = self.literalFactory(len(data), self.deferred)
        leftover = literal.write(data)

        self.assertIsInstance(leftover, bytes)
        self.assertFalse(leftover)
        self.assertNoResult(self.deferred)

    def test_overlongWrite(self):
        """
        The literal returns any left over L{bytes} when given more
        data than the literal requires.
        """
        data = b"completeleftover"
        literal = self.literalFactory(len(b"complete"), self.deferred)

        leftover = literal.write(data)

        self.assertEqual(leftover, b"leftover")

    def test_emptyLiteral(self):
        """
        The literal returns an empty L{bytes} instance
        when given an empty L{bytes} instance.
        """
        literal = self.literalFactory(0, self.deferred)
        data = b"leftover"

        leftover = literal.write(data)

        self.assertEqual(leftover, data)


class LiteralStringTests(LiteralTestsMixin, SynchronousTestCase):
    """
    Tests for L{self.literalFactory}.
    """

    literalFactory = imap4.LiteralString

    def test_callback(self):
        """
        Calling L{imap4.LiteralString.callback} with a line fires the
        instance's L{Deferred} with a 2-L{tuple} whose first element
        is the collected data and whose second is the provided line.
        """
        data = b"data"
        extra = b"extra"

        literal = imap4.LiteralString(len(data), self.deferred)

        for c in iterbytes(data):
            literal.write(c)

        literal.callback(b"extra")

        result = self.successResultOf(self.deferred)
        self.assertEqual(result, (data, extra))


class LiteralFileTests(LiteralTestsMixin, TestCase):
    """
    Tests for L{imap4.LiteralFile}.
    """

    literalFactory = imap4.LiteralFile

    def test_callback(self):
        """
        Calling L{imap4.LiteralFile.callback} with a line fires the
        instance's L{Deferred} with a 2-L{tuple} whose first element
        is the file and whose second is the provided line.
        """
        data = b"data"
        extra = b"extra"

        literal = imap4.LiteralFile(len(data), self.deferred)

        for c in iterbytes(data):
            literal.write(c)

        literal.callback(b"extra")

        result = self.successResultOf(self.deferred)
        self.assertEqual(len(result), 2)

        dataFile, extra = result
        self.assertEqual(dataFile.read(), b"data")

    def test_callbackSpooledToDisk(self):
        """
        A L{imap4.LiteralFile} whose size exceeds the maximum
        in-memory size spools its content to disk, and invoking its
        L{callback} with a line fires the instance's L{Deferred} with
        a 2-L{tuple} whose first element is the spooled file and whose second
        is the provided line.
        """
        data = b"data"
        extra = b"extra"

        self.patch(imap4.LiteralFile, "_memoryFileLimit", 1)

        literal = imap4.LiteralFile(len(data), self.deferred)

        for c in iterbytes(data):
            literal.write(c)

        literal.callback(b"extra")

        result = self.successResultOf(self.deferred)
        self.assertEqual(len(result), 2)

        dataFile, extra = result
        self.assertEqual(dataFile.read(), b"data")


class WriteBufferTests(SynchronousTestCase):
    """
    Tests for L{imap4.WriteBuffer}.
    """

    def setUp(self):
        self.transport = StringTransport()

    def test_partialWrite(self):
        """
        L{imap4.WriteBuffer} buffers writes that are smaller than its
        buffer size.
        """
        buf = imap4.WriteBuffer(self.transport)
        data = b"x" * buf.bufferSize

        buf.write(data)

        self.assertFalse(self.transport.value())

    def test_overlongWrite(self):
        """
        L{imap4.WriteBuffer} writes data without buffering it when
        the size of the data exceeds the size of its buffer.
        """
        buf = imap4.WriteBuffer(self.transport)
        data = b"x" * (buf.bufferSize + 1)

        buf.write(data)

        self.assertEqual(self.transport.value(), data)

    def test_writesImplyFlush(self):
        """
        L{imap4.WriteBuffer} buffers writes until its buffer's size
        exceeds its maximum value.
        """
        buf = imap4.WriteBuffer(self.transport)
        firstData = b"x" * buf.bufferSize
        secondData = b"y"

        buf.write(firstData)

        self.assertFalse(self.transport.value())

        buf.write(secondData)

        self.assertEqual(self.transport.value(), firstData + secondData)

    def test_explicitFlush(self):
        """
        L{imap4.WriteBuffer.flush} flushes the buffer even when its
        size is smaller than the buffer size.
        """
        buf = imap4.WriteBuffer(self.transport)
        data = b"x" * (buf.bufferSize)

        buf.write(data)

        self.assertFalse(self.transport.value())

        buf.flush()

        self.assertEqual(self.transport.value(), data)

    def test_explicitFlushEmptyBuffer(self):
        """
        L{imap4.WriteBuffer.flush} has no effect if when the buffer is
        empty.
        """
        buf = imap4.WriteBuffer(self.transport)

        buf.flush()

        self.assertFalse(self.transport.value())

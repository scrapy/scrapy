# -*- test-case-name: twisted.mail.test.test_bounce -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Support for bounce message generation.
"""
import email.utils
import os
import time
from io import SEEK_END, SEEK_SET, StringIO

from twisted.mail import smtp

BOUNCE_FORMAT = """\
From: postmaster@{failedDomain}
To: {failedFrom}
Subject: Returned Mail: see transcript for details
Message-ID: {messageID}
Content-Type: multipart/report; report-type=delivery-status;
    boundary="{boundary}"

--{boundary}

{transcript}

--{boundary}
Content-Type: message/delivery-status
Arrival-Date: {ctime}
Final-Recipient: RFC822; {failedTo}
"""


def generateBounce(message, failedFrom, failedTo, transcript="", encoding="utf-8"):
    """
    Generate a bounce message for an undeliverable email message.

    @type message: a file-like object
    @param message: The undeliverable message.

    @type failedFrom: L{bytes} or L{unicode}
    @param failedFrom: The originator of the undeliverable message.

    @type failedTo: L{bytes} or L{unicode}
    @param failedTo: The destination of the undeliverable message.

    @type transcript: L{bytes} or L{unicode}
    @param transcript: An error message to include in the bounce message.

    @type encoding: L{str} or L{unicode}
    @param encoding: Encoding to use, default: utf-8

    @rtype: 3-L{tuple} of (E{1}) L{bytes}, (E{2}) L{bytes}, (E{3}) L{bytes}
    @return: The originator, the destination and the contents of the bounce
        message.  The destination of the bounce message is the originator of
        the undeliverable message.
    """

    if isinstance(failedFrom, bytes):
        failedFrom = failedFrom.decode(encoding)

    if isinstance(failedTo, bytes):
        failedTo = failedTo.decode(encoding)

    if not transcript:
        transcript = """\
I'm sorry, the following address has permanent errors: {failedTo}.
I've given up, and I will not retry the message again.
""".format(
            failedTo=failedTo
        )

    failedAddress = email.utils.parseaddr(failedTo)[1]
    data = {
        "boundary": "{}_{}_{}".format(time.time(), os.getpid(), "XXXXX"),
        "ctime": time.ctime(time.time()),
        "failedAddress": failedAddress,
        "failedDomain": failedAddress.split("@", 1)[1],
        "failedFrom": failedFrom,
        "failedTo": failedTo,
        "messageID": smtp.messageid(uniq="bounce"),
        "message": message,
        "transcript": transcript,
    }

    fp = StringIO()
    fp.write(BOUNCE_FORMAT.format(**data))
    orig = message.tell()
    message.seek(0, SEEK_END)
    sz = message.tell()
    message.seek(orig, SEEK_SET)
    if sz > 10000:
        while 1:
            line = message.readline()
            if isinstance(line, bytes):
                line = line.decode(encoding)
            if len(line) <= 0:
                break
            fp.write(line)
    else:
        messageContent = message.read()
        if isinstance(messageContent, bytes):
            messageContent = messageContent.decode(encoding)
        fp.write(messageContent)
    return b"", failedFrom.encode(encoding), fp.getvalue().encode(encoding)

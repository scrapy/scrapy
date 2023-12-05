# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.application.service import ServiceMaker

TwistedMail = ServiceMaker(
    "Twisted Mail", "twisted.mail.tap", "An email service", "mail"
)

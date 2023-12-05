# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.application.service import ServiceMaker

TwistedSOCKS = ServiceMaker(
    "Twisted SOCKS", "twisted.tap.socks", "A SOCKSv4 proxy service.", "socks"
)

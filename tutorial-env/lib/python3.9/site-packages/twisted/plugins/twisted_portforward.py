# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.application.service import ServiceMaker

TwistedPortForward = ServiceMaker(
    "Twisted Port-Forwarding",
    "twisted.tap.portforward",
    "A simple port-forwarder.",
    "portforward",
)

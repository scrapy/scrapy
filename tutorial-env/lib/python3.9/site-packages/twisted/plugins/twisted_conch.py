# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.application.service import ServiceMaker

TwistedSSH = ServiceMaker(
    "Twisted Conch Server", "twisted.conch.tap", "A Conch SSH service.", "conch"
)

TwistedManhole = ServiceMaker(
    "Twisted Manhole (new)",
    "twisted.conch.manhole_tap",
    (
        "An interactive remote debugger service accessible via telnet "
        "and ssh and providing syntax coloring and basic line editing "
        "functionality."
    ),
    "manhole",
)

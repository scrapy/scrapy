# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.application.service import ServiceMaker

TwistedWeb = ServiceMaker(
    "Twisted Web",
    "twisted.web.tap",
    (
        "A general-purpose web server which can serve from a "
        "filesystem or application resource."
    ),
    "web",
)

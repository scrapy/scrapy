# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.application.service import ServiceMaker

TwistedProcmon = ServiceMaker(
    "Twisted Process Monitor",
    "twisted.runner.procmontap",
    ("A process watchdog / supervisor"),
    "procmon",
)

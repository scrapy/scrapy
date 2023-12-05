# -*- test-case-name: twisted.runner.test.test_procmontap -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Support for creating a service which runs a process monitor.
"""

from typing import List, Sequence

from twisted.python import usage
from twisted.runner.procmon import ProcessMonitor


class Options(usage.Options):
    """
    Define the options accepted by the I{twistd procmon} plugin.
    """

    synopsis = "[procmon options] commandline"

    optParameters = [
        [
            "threshold",
            "t",
            1,
            "How long a process has to live "
            "before the death is considered instant, in seconds.",
            float,
        ],
        [
            "killtime",
            "k",
            5,
            "How long a process being killed "
            "has to get its affairs in order before it gets killed "
            "with an unmaskable signal.",
            float,
        ],
        [
            "minrestartdelay",
            "m",
            1,
            "The minimum time (in "
            "seconds) to wait before attempting to restart a "
            "process",
            float,
        ],
        [
            "maxrestartdelay",
            "M",
            3600,
            "The maximum time (in "
            "seconds) to wait before attempting to restart a "
            "process",
            float,
        ],
    ]

    optFlags: List[Sequence[str]] = []

    longdesc = """\
procmon runs processes, monitors their progress, and restarts them when they
die.

procmon will not attempt to restart a process that appears to die instantly;
with each "instant" death (less than 1 second, by default), it will delay
approximately twice as long before restarting it. A successful run will reset
the counter.

Eg twistd procmon sleep 10"""

    def parseArgs(self, *args):
        """
        Grab the command line that is going to be started and monitored
        """
        self["args"] = args

    def postOptions(self):
        """
        Check for dependencies.
        """
        if len(self["args"]) < 1:
            raise usage.UsageError("Please specify a process commandline")


def makeService(config):
    s = ProcessMonitor()

    s.threshold = config["threshold"]
    s.killTime = config["killtime"]
    s.minRestartDelay = config["minrestartdelay"]
    s.maxRestartDelay = config["maxrestartdelay"]

    s.addProcess(" ".join(config["args"]), config["args"])
    return s

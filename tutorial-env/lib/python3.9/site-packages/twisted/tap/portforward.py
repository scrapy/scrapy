# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Support module for making a port forwarder with twistd.
"""
from twisted.application import strports
from twisted.protocols import portforward
from twisted.python import usage


class Options(usage.Options):
    synopsis = "[options]"
    longdesc = "Port Forwarder."
    optParameters = [
        ["port", "p", "6666", "Set the port number."],
        ["host", "h", "localhost", "Set the host."],
        ["dest_port", "d", 6665, "Set the destination port."],
    ]

    compData = usage.Completions(optActions={"host": usage.CompleteHostnames()})


def makeService(config):
    f = portforward.ProxyFactory(config["host"], int(config["dest_port"]))
    return strports.service(config["port"], f)

# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
I am a support module for making SOCKSv4 servers with twistd.
"""

from twisted.application import internet
from twisted.protocols import socks
from twisted.python import usage


class Options(usage.Options):
    synopsis = "[-i <interface>] [-p <port>] [-l <file>]"
    optParameters = [
        ["interface", "i", "127.0.0.1", "local interface to which we listen"],
        ["port", "p", 1080, "Port on which to listen"],
        ["log", "l", None, "file to log connection data to"],
    ]

    compData = usage.Completions(
        optActions={
            "log": usage.CompleteFiles("*.log"),
            "interface": usage.CompleteNetInterfaces(),
        }
    )

    longdesc = "Makes a SOCKSv4 server."


def makeService(config):
    if config["interface"] != "127.0.0.1":
        print()
        print("WARNING:")
        print("  You have chosen to listen on a non-local interface.")
        print("  This may allow intruders to access your local network")
        print("  if you run this on a firewall.")
        print()
    t = socks.SOCKSv4Factory(config["log"])
    portno = int(config["port"])
    return internet.TCPServer(portno, t, interface=config["interface"])

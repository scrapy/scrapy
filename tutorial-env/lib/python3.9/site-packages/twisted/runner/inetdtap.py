# -*- test-case-name: twisted.runner.test.test_inetdtap -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted inetd TAP support

The purpose of inetdtap is to provide an inetd-like server, to allow Twisted to
invoke other programs to handle incoming sockets.
This is a useful thing as a "networking swiss army knife" tool, like netcat.
"""

import grp
import pwd
import socket

from twisted.application import internet, service as appservice
from twisted.internet.protocol import ServerFactory
from twisted.python import log, usage
from twisted.runner import inetd, inetdconf

# Protocol map
protocolDict = {"tcp": socket.IPPROTO_TCP, "udp": socket.IPPROTO_UDP}


class Options(usage.Options):
    """
    To use it, create a file named `sample-inetd.conf` with:

    8123 stream tcp wait some_user /bin/cat -

    You can then run it as in the following example and port 8123 became an
    echo server.

    twistd -n inetd -f sample-inetd.conf
    """

    optParameters = [
        ["rpc", "r", "/etc/rpc", "DEPRECATED. RPC procedure table file"],
        ["file", "f", "/etc/inetd.conf", "Service configuration file"],
    ]

    optFlags = [["nointernal", "i", "Don't run internal services"]]

    compData = usage.Completions(optActions={"file": usage.CompleteFiles("*.conf")})


def makeService(config):
    s = appservice.MultiService()
    conf = inetdconf.InetdConf()
    with open(config["file"]) as f:
        conf.parseFile(f)

    for service in conf.services:
        protocol = service.protocol

        if service.protocol.startswith("rpc/"):
            log.msg("Skipping rpc service due to lack of rpc support")
            continue

        if (protocol, service.socketType) not in [("tcp", "stream"), ("udp", "dgram")]:
            log.msg(
                "Skipping unsupported type/protocol: %s/%s"
                % (service.socketType, service.protocol)
            )
            continue

        # Convert the username into a uid (if necessary)
        try:
            service.user = int(service.user)
        except ValueError:
            try:
                service.user = pwd.getpwnam(service.user)[2]
            except KeyError:
                log.msg("Unknown user: " + service.user)
                continue

        # Convert the group name into a gid (if necessary)
        if service.group is None:
            # If no group was specified, use the user's primary group
            service.group = pwd.getpwuid(service.user)[3]
        else:
            try:
                service.group = int(service.group)
            except ValueError:
                try:
                    service.group = grp.getgrnam(service.group)[2]
                except KeyError:
                    log.msg("Unknown group: " + service.group)
                    continue

        if service.program == "internal":
            if config["nointernal"]:
                continue

            # Internal services can use a standard ServerFactory
            if service.name not in inetd.internalProtocols:
                log.msg("Unknown internal service: " + service.name)
                continue
            factory = ServerFactory()
            factory.protocol = inetd.internalProtocols[service.name]
        else:
            factory = inetd.InetdFactory(service)

        if protocol == "tcp":
            internet.TCPServer(service.port, factory).setServiceParent(s)
        elif protocol == "udp":
            raise RuntimeError("not supporting UDP")
    return s

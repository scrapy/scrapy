# -*- test-case-name: twisted.names.test.test_tap -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Domain Name Server
"""

import os
import traceback

from twisted.application import internet, service
from twisted.names import authority, dns, secondary, server
from twisted.python import usage


class Options(usage.Options):
    optParameters = [
        ["interface", "i", "", "The interface to which to bind"],
        ["port", "p", "53", "The port on which to listen"],
        [
            "resolv-conf",
            None,
            None,
            "Override location of resolv.conf (implies --recursive)",
        ],
        ["hosts-file", None, None, "Perform lookups with a hosts file"],
    ]

    optFlags = [
        ["cache", "c", "Enable record caching"],
        ["recursive", "r", "Perform recursive lookups"],
        ["verbose", "v", "Log verbosely"],
    ]

    compData = usage.Completions(
        optActions={"interface": usage.CompleteNetInterfaces()}
    )

    zones = None
    zonefiles = None

    def __init__(self):
        usage.Options.__init__(self)
        self["verbose"] = 0
        self.bindfiles = []
        self.zonefiles = []
        self.secondaries = []

    def opt_pyzone(self, filename):
        """Specify the filename of a Python syntax zone definition"""
        if not os.path.exists(filename):
            raise usage.UsageError(filename + ": No such file")
        self.zonefiles.append(filename)

    def opt_bindzone(self, filename):
        """Specify the filename of a BIND9 syntax zone definition"""
        if not os.path.exists(filename):
            raise usage.UsageError(filename + ": No such file")
        self.bindfiles.append(filename)

    def opt_secondary(self, ip_domain):
        """Act as secondary for the specified domain, performing
        zone transfers from the specified IP (IP/domain)
        """
        args = ip_domain.split("/", 1)
        if len(args) != 2:
            raise usage.UsageError("Argument must be of the form IP[:port]/domain")
        address = args[0].split(":")
        if len(address) == 1:
            address = (address[0], dns.PORT)
        else:
            try:
                port = int(address[1])
            except ValueError:
                raise usage.UsageError(
                    f"Specify an integer port number, not {address[1]!r}"
                )
            address = (address[0], port)
        self.secondaries.append((address, [args[1]]))

    def opt_verbose(self):
        """Increment verbosity level"""
        self["verbose"] += 1

    def postOptions(self):
        if self["resolv-conf"]:
            self["recursive"] = True

        self.svcs = []
        self.zones = []
        for f in self.zonefiles:
            try:
                self.zones.append(authority.PySourceAuthority(f))
            except Exception:
                traceback.print_exc()
                raise usage.UsageError("Invalid syntax in " + f)
        for f in self.bindfiles:
            try:
                self.zones.append(authority.BindAuthority(f))
            except Exception:
                traceback.print_exc()
                raise usage.UsageError("Invalid syntax in " + f)
        for f in self.secondaries:
            svc = secondary.SecondaryAuthorityService.fromServerAddressAndDomains(*f)
            self.svcs.append(svc)
            self.zones.append(self.svcs[-1].getAuthority())
        try:
            self["port"] = int(self["port"])
        except ValueError:
            raise usage.UsageError("Invalid port: {!r}".format(self["port"]))


def _buildResolvers(config):
    """
    Build DNS resolver instances in an order which leaves recursive
    resolving as a last resort.

    @type config: L{Options} instance
    @param config: Parsed command-line configuration

    @return: Two-item tuple of a list of cache resovers and a list of client
        resolvers
    """
    from twisted.names import cache, client, hosts

    ca, cl = [], []
    if config["cache"]:
        ca.append(cache.CacheResolver(verbose=config["verbose"]))
    if config["hosts-file"]:
        cl.append(hosts.Resolver(file=config["hosts-file"]))
    if config["recursive"]:
        cl.append(client.createResolver(resolvconf=config["resolv-conf"]))
    return ca, cl


def makeService(config):
    ca, cl = _buildResolvers(config)

    f = server.DNSServerFactory(config.zones, ca, cl, config["verbose"])
    p = dns.DNSDatagramProtocol(f)
    f.noisy = 0
    ret = service.MultiService()
    for (klass, arg) in [(internet.TCPServer, f), (internet.UDPServer, p)]:
        s = klass(config["port"], arg, interface=config["interface"])
        s.setServiceParent(ret)
    for svc in config.svcs:
        svc.setServiceParent(ret)
    return ret

# -*- test-case-name: twisted.words.test.test_tap -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
"""
Shiny new words service maker
"""

import socket
import sys
from typing import List, Optional, Sequence

from twisted import plugin
from twisted.application import strports
from twisted.application.service import MultiService
from twisted.cred import checkers, credentials, portal, strcred
from twisted.python import usage
from twisted.words import iwords, service


class Options(usage.Options, strcred.AuthOptionMixin):
    supportedInterfaces = [credentials.IUsernamePassword]
    optParameters: List[Sequence[Optional[str]]] = [
        (
            "hostname",
            None,
            socket.gethostname(),
            "Name of this server; purely an informative",
        )
    ]

    compData = usage.Completions(multiUse=["group"])

    interfacePlugins = {}
    plg = None
    for plg in plugin.getPlugins(iwords.IProtocolPlugin):
        assert plg.name not in interfacePlugins
        interfacePlugins[plg.name] = plg
        optParameters.append(
            (
                plg.name + "-port",
                None,
                None,
                "strports description of the port to bind for the  "
                + plg.name
                + " server",
            )
        )
    del plg

    def __init__(self, *a, **kw):
        usage.Options.__init__(self, *a, **kw)
        self["groups"] = []

    def opt_group(self, name):
        """Specify a group which should exist"""
        self["groups"].append(name.decode(sys.stdin.encoding))

    def opt_passwd(self, filename):
        """
        Name of a passwd-style file. (This is for
        backwards-compatibility only; you should use the --auth
        command instead.)
        """
        self.addChecker(checkers.FilePasswordDB(filename))


def makeService(config):
    credCheckers = config.get("credCheckers", [])
    wordsRealm = service.InMemoryWordsRealm(config["hostname"])
    wordsPortal = portal.Portal(wordsRealm, credCheckers)

    msvc = MultiService()

    # XXX Attribute lookup on config is kind of bad - hrm.
    for plgName in config.interfacePlugins:
        port = config.get(plgName + "-port")
        if port is not None:
            factory = config.interfacePlugins[plgName].getFactory(
                wordsRealm, wordsPortal
            )
            svc = strports.service(port, factory)
            svc.setServiceParent(msvc)

    # This is bogus.  createGroup is async.  makeService must be
    # allowed to return a Deferred or some crap.
    for g in config["groups"]:
        wordsRealm.createGroup(g)

    return msvc

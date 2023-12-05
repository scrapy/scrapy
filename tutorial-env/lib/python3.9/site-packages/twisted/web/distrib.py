# -*- test-case-name: twisted.web.test.test_distrib -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Distributed web servers.

This is going to have to be refactored so that argument parsing is done
by each subprocess and not by the main web server (i.e. GET, POST etc.).
"""

import copy
import os
import sys

try:
    import pwd
except ImportError:
    pwd = None  # type: ignore[assignment]
from io import BytesIO
from xml.dom.minidom import getDOMImplementation

from twisted.internet import address, reactor
from twisted.logger import Logger
from twisted.persisted import styles
from twisted.spread import pb
from twisted.spread.banana import SIZE_LIMIT
from twisted.web import http, resource, server, static, util
from twisted.web.http_headers import Headers


class _ReferenceableProducerWrapper(pb.Referenceable):
    def __init__(self, producer):
        self.producer = producer

    def remote_resumeProducing(self):
        self.producer.resumeProducing()

    def remote_pauseProducing(self):
        self.producer.pauseProducing()

    def remote_stopProducing(self):
        self.producer.stopProducing()


class Request(pb.RemoteCopy, server.Request):
    """
    A request which was received by a L{ResourceSubscription} and sent via
    PB to a distributed node.
    """

    def setCopyableState(self, state):
        """
        Initialize this L{twisted.web.distrib.Request} based on the copied
        state so that it closely resembles a L{twisted.web.server.Request}.
        """
        for k in "host", "client":
            tup = state[k]
            addrdesc = {"INET": "TCP", "UNIX": "UNIX"}[tup[0]]
            addr = {
                "TCP": lambda: address.IPv4Address(addrdesc, tup[1], tup[2]),
                "UNIX": lambda: address.UNIXAddress(tup[1]),
            }[addrdesc]()
            state[k] = addr
        state["requestHeaders"] = Headers(dict(state["requestHeaders"]))
        pb.RemoteCopy.setCopyableState(self, state)
        # Emulate the local request interface --
        self.content = BytesIO(self.content_data)
        self.finish = self.remote.remoteMethod("finish")
        self.setHeader = self.remote.remoteMethod("setHeader")
        self.addCookie = self.remote.remoteMethod("addCookie")
        self.setETag = self.remote.remoteMethod("setETag")
        self.setResponseCode = self.remote.remoteMethod("setResponseCode")
        self.setLastModified = self.remote.remoteMethod("setLastModified")

        # To avoid failing if a resource tries to write a very long string
        # all at once, this one will be handled slightly differently.
        self._write = self.remote.remoteMethod("write")

    def write(self, bytes):
        """
        Write the given bytes to the response body.

        @param bytes: The bytes to write.  If this is longer than 640k, it
            will be split up into smaller pieces.
        """
        start = 0
        end = SIZE_LIMIT
        while True:
            self._write(bytes[start:end])
            start += SIZE_LIMIT
            end += SIZE_LIMIT
            if start >= len(bytes):
                break

    def registerProducer(self, producer, streaming):
        self.remote.callRemote(
            "registerProducer", _ReferenceableProducerWrapper(producer), streaming
        ).addErrback(self.fail)

    def unregisterProducer(self):
        self.remote.callRemote("unregisterProducer").addErrback(self.fail)

    def fail(self, failure):
        self._log.failure("", failure=failure)


pb.setUnjellyableForClass(server.Request, Request)


class Issue:
    _log = Logger()

    def __init__(self, request):
        self.request = request

    def finished(self, result):
        if result is not server.NOT_DONE_YET:
            assert isinstance(result, str), "return value not a string"
            self.request.write(result)
            self.request.finish()

    def failed(self, failure):
        # XXX: Argh. FIXME.
        failure = str(failure)
        self.request.write(
            resource._UnsafeErrorPage(
                http.INTERNAL_SERVER_ERROR,
                "Server Connection Lost",
                # GHSA-vg46-2rrj-3647 note: _PRE does HTML-escape the input.
                "Connection to distributed server lost:" + util._PRE(failure),
            ).render(self.request)
        )
        self.request.finish()
        self._log.info(failure)


class ResourceSubscription(resource.Resource):
    isLeaf = 1
    waiting = 0
    _log = Logger()

    def __init__(self, host, port):
        resource.Resource.__init__(self)
        self.host = host
        self.port = port
        self.pending = []
        self.publisher = None

    def __getstate__(self):
        """Get persistent state for this ResourceSubscription."""
        # When I unserialize,
        state = copy.copy(self.__dict__)
        # Publisher won't be connected...
        state["publisher"] = None
        # I won't be making a connection
        state["waiting"] = 0
        # There will be no pending requests.
        state["pending"] = []
        return state

    def connected(self, publisher):
        """I've connected to a publisher; I'll now send all my requests."""
        self._log.info("connected to publisher")
        publisher.broker.notifyOnDisconnect(self.booted)
        self.publisher = publisher
        self.waiting = 0
        for request in self.pending:
            self.render(request)
        self.pending = []

    def notConnected(self, msg):
        """I can't connect to a publisher; I'll now reply to all pending
        requests.
        """
        self._log.info("could not connect to distributed web service: {msg}", msg=msg)
        self.waiting = 0
        self.publisher = None
        for request in self.pending:
            request.write("Unable to connect to distributed server.")
            request.finish()
        self.pending = []

    def booted(self):
        self.notConnected("connection dropped")

    def render(self, request):
        """Render this request, from my server.

        This will always be asynchronous, and therefore return NOT_DONE_YET.
        It spins off a request to the pb client, and either adds it to the list
        of pending issues or requests it immediately, depending on if the
        client is already connected.
        """
        if not self.publisher:
            self.pending.append(request)
            if not self.waiting:
                self.waiting = 1
                bf = pb.PBClientFactory()
                timeout = 10
                if self.host == "unix":
                    reactor.connectUNIX(self.port, bf, timeout)
                else:
                    reactor.connectTCP(self.host, self.port, bf, timeout)
                d = bf.getRootObject()
                d.addCallbacks(self.connected, self.notConnected)

        else:
            i = Issue(request)
            self.publisher.callRemote("request", request).addCallbacks(
                i.finished, i.failed
            )
        return server.NOT_DONE_YET


class ResourcePublisher(pb.Root, styles.Versioned):
    """
    L{ResourcePublisher} exposes a remote API which can be used to respond
    to request.

    @ivar site: The site which will be used for resource lookup.
    @type site: L{twisted.web.server.Site}
    """

    _log = Logger()

    def __init__(self, site):
        self.site = site

    persistenceVersion = 2

    def upgradeToVersion2(self):
        self.application.authorizer.removeIdentity("web")
        del self.application.services[self.serviceName]
        del self.serviceName
        del self.application
        del self.perspectiveName

    def getPerspectiveNamed(self, name):
        return self

    def remote_request(self, request):
        """
        Look up the resource for the given request and render it.
        """
        res = self.site.getResourceFor(request)
        self._log.info(request)
        result = res.render(request)
        if result is not server.NOT_DONE_YET:
            request.write(result)
            request.finish()
        return server.NOT_DONE_YET


class UserDirectory(resource.Resource):
    """
    A resource which lists available user resources and serves them as
    children.

    @ivar _pwd: An object like L{pwd} which is used to enumerate users and
        their home directories.
    """

    userDirName = "public_html"
    userSocketName = ".twistd-web-pb"

    template = """
<html>
    <head>
    <title>twisted.web.distrib.UserDirectory</title>
    <style>

    a
    {
        font-family: Lucida, Verdana, Helvetica, Arial, sans-serif;
        color: #369;
        text-decoration: none;
    }

    th
    {
        font-family: Lucida, Verdana, Helvetica, Arial, sans-serif;
        font-weight: bold;
        text-decoration: none;
        text-align: left;
    }

    pre, code
    {
        font-family: "Courier New", Courier, monospace;
    }

    p, body, td, ol, ul, menu, blockquote, div
    {
        font-family: Lucida, Verdana, Helvetica, Arial, sans-serif;
        color: #000;
    }
    </style>
    </head>

    <body>
    <h1>twisted.web.distrib.UserDirectory</h1>

    %(users)s
</body>
</html>
"""

    def __init__(self, userDatabase=None):
        resource.Resource.__init__(self)
        if userDatabase is None:
            userDatabase = pwd
        self._pwd = userDatabase

    def _users(self):
        """
        Return a list of two-tuples giving links to user resources and text to
        associate with those links.
        """
        users = []
        for user in self._pwd.getpwall():
            name, passwd, uid, gid, gecos, dir, shell = user
            realname = gecos.split(",")[0]
            if not realname:
                realname = name
            if os.path.exists(os.path.join(dir, self.userDirName)):
                users.append((name, realname + " (file)"))
            twistdsock = os.path.join(dir, self.userSocketName)
            if os.path.exists(twistdsock):
                linkName = name + ".twistd"
                users.append((linkName, realname + " (twistd)"))
        return users

    def render_GET(self, request):
        """
        Render as HTML a listing of all known users with links to their
        personal resources.
        """

        domImpl = getDOMImplementation()
        newDoc = domImpl.createDocument(None, "ul", None)
        listing = newDoc.documentElement
        for link, text in self._users():
            linkElement = newDoc.createElement("a")
            linkElement.setAttribute("href", link + "/")
            textNode = newDoc.createTextNode(text)
            linkElement.appendChild(textNode)
            item = newDoc.createElement("li")
            item.appendChild(linkElement)
            listing.appendChild(item)

        htmlDoc = self.template % ({"users": listing.toxml()})
        return htmlDoc.encode("utf-8")

    def getChild(self, name, request):
        if name == b"":
            return self

        td = b".twistd"

        if name.endswith(td):
            username = name[: -len(td)]
            sub = 1
        else:
            username = name
            sub = 0
        try:
            # Decode using the filesystem encoding to reverse a transformation
            # done in the pwd module.
            (
                pw_name,
                pw_passwd,
                pw_uid,
                pw_gid,
                pw_gecos,
                pw_dir,
                pw_shell,
            ) = self._pwd.getpwnam(username.decode(sys.getfilesystemencoding()))
        except KeyError:
            return resource._UnsafeNoResource()
        if sub:
            twistdsock = os.path.join(pw_dir, self.userSocketName)
            rs = ResourceSubscription("unix", twistdsock)
            self.putChild(name, rs)
            return rs
        else:
            path = os.path.join(pw_dir, self.userDirName)
            if not os.path.exists(path):
                return resource._UnsafeNoResource()
            return static.File(path)

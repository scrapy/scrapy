# -*- test-case-name: twisted.web.test.test_web -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This is a web-server which integrates with the twisted.internet
infrastructure.
"""

from __future__ import division, absolute_import

import copy
import os
try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote as _quote

    def quote(string, *args, **kwargs):
        return _quote(
            string.decode('charmap'), *args, **kwargs).encode('charmap')

import zlib
from binascii import hexlify

from zope.interface import implementer

from twisted.python.compat import _PY3, networkString, nativeString, intToBytes
if _PY3:
    class Copyable:
        """
        Fake mixin, until twisted.spread is ported.
        """
else:
    from twisted.spread.pb import Copyable, ViewPoint
from twisted.internet import address, interfaces
from twisted.web import iweb, http, util
from twisted.web.http import unquote
from twisted.python import log, reflect, failure, components
from twisted import copyright
from twisted.web import resource
from twisted.web.error import UnsupportedMethod

from twisted.python.versions import Version
from twisted.python.deprecate import deprecatedModuleAttribute
from twisted.python.compat import escape

NOT_DONE_YET = 1

__all__ = [
    'supportedMethods',
    'Request',
    'Session',
    'Site',
    'version',
    'NOT_DONE_YET',
    'GzipEncoderFactory'
]


# backwards compatibility
deprecatedModuleAttribute(
    Version("Twisted", 12, 1, 0),
    "Please use twisted.web.http.datetimeToString instead",
    "twisted.web.server",
    "date_time_string")
deprecatedModuleAttribute(
    Version("Twisted", 12, 1, 0),
    "Please use twisted.web.http.stringToDatetime instead",
    "twisted.web.server",
    "string_date_time")
date_time_string = http.datetimeToString
string_date_time = http.stringToDatetime

# Support for other methods may be implemented on a per-resource basis.
supportedMethods = (b'GET', b'HEAD', b'POST')


def _addressToTuple(addr):
    if isinstance(addr, address.IPv4Address):
        return ('INET', addr.host, addr.port)
    elif isinstance(addr, address.UNIXAddress):
        return ('UNIX', addr.name)
    else:
        return tuple(addr)



@implementer(iweb.IRequest)
class Request(Copyable, http.Request, components.Componentized):
    """
    An HTTP request.

    @ivar defaultContentType: A C{bytes} giving the default I{Content-Type}
        value to send in responses if no other value is set.  L{None} disables
        the default.

    @ivar _insecureSession: The L{Session} object representing state that will
        be transmitted over plain-text HTTP.

    @ivar _secureSession: The L{Session} object representing the state that
        will be transmitted only over HTTPS.
    """

    defaultContentType = b"text/html"

    site = None
    appRootURL = None
    __pychecker__ = 'unusednames=issuer'
    _inFakeHead = False
    _encoder = None

    def __init__(self, *args, **kw):
        http.Request.__init__(self, *args, **kw)
        components.Componentized.__init__(self)


    def getStateToCopyFor(self, issuer):
        x = self.__dict__.copy()
        del x['transport']
        # XXX refactor this attribute out; it's from protocol
        # del x['server']
        del x['channel']
        del x['content']
        del x['site']
        self.content.seek(0, 0)
        x['content_data'] = self.content.read()
        x['remote'] = ViewPoint(issuer, self)

        # Address objects aren't jellyable
        x['host'] = _addressToTuple(x['host'])
        x['client'] = _addressToTuple(x['client'])

        # Header objects also aren't jellyable.
        x['requestHeaders'] = list(x['requestHeaders'].getAllRawHeaders())

        return x

    # HTML generation helpers


    def sibLink(self, name):
        """
        Return the text that links to a sibling of the requested resource.
        """
        if self.postpath:
            return (len(self.postpath)*b"../") + name
        else:
            return name


    def childLink(self, name):
        """
        Return the text that links to a child of the requested resource.
        """
        lpp = len(self.postpath)
        if lpp > 1:
            return ((lpp-1)*b"../") + name
        elif lpp == 1:
            return name
        else:  # lpp == 0
            if len(self.prepath) and self.prepath[-1]:
                return self.prepath[-1] + b'/' + name
            else:
                return name


    def process(self):
        """
        Process a request.
        """

        # get site from channel
        self.site = self.channel.site

        # set various default headers
        self.setHeader(b'server', version)
        self.setHeader(b'date', http.datetimeToString())

        # Resource Identification
        self.prepath = []
        self.postpath = list(map(unquote, self.path[1:].split(b'/')))

        try:
            resrc = self.site.getResourceFor(self)
            if resource._IEncodingResource.providedBy(resrc):
                encoder = resrc.getEncoder(self)
                if encoder is not None:
                    self._encoder = encoder
            self.render(resrc)
        except:
            self.processingFailed(failure.Failure())


    def write(self, data):
        """
        Write data to the transport (if not responding to a HEAD request).

        @param data: A string to write to the response.
        """
        if not self.startedWriting:
            # Before doing the first write, check to see if a default
            # Content-Type header should be supplied.
            modified = self.code != http.NOT_MODIFIED
            contentType = self.responseHeaders.getRawHeaders(b'content-type')
            if (modified and contentType is None and
                self.defaultContentType is not None
                    ):
                self.responseHeaders.setRawHeaders(
                    b'content-type', [self.defaultContentType])

        # Only let the write happen if we're not generating a HEAD response by
        # faking out the request method.  Note, if we are doing that,
        # startedWriting will never be true, and the above logic may run
        # multiple times.  It will only actually change the responseHeaders
        # once though, so it's still okay.
        if not self._inFakeHead:
            if self._encoder:
                data = self._encoder.encode(data)
            http.Request.write(self, data)


    def finish(self):
        """
        Override C{http.Request.finish} for possible encoding.
        """
        if self._encoder:
            data = self._encoder.finish()
            if data:
                http.Request.write(self, data)
        return http.Request.finish(self)


    def render(self, resrc):
        """
        Ask a resource to render itself.

        @param resrc: a L{twisted.web.resource.IResource}.
        """
        try:
            body = resrc.render(self)
        except UnsupportedMethod as e:
            allowedMethods = e.allowedMethods
            if (self.method == b"HEAD") and (b"GET" in allowedMethods):
                # We must support HEAD (RFC 2616, 5.1.1).  If the
                # resource doesn't, fake it by giving the resource
                # a 'GET' request and then return only the headers,
                # not the body.
                log.msg("Using GET to fake a HEAD request for %s" %
                        (resrc,))
                self.method = b"GET"
                self._inFakeHead = True
                body = resrc.render(self)

                if body is NOT_DONE_YET:
                    log.msg("Tried to fake a HEAD request for %s, but "
                            "it got away from me." % resrc)
                    # Oh well, I guess we won't include the content length.
                else:
                    self.setHeader(b'content-length', intToBytes(len(body)))

                self._inFakeHead = False
                self.method = b"HEAD"
                self.write(b'')
                self.finish()
                return

            if self.method in (supportedMethods):
                # We MUST include an Allow header
                # (RFC 2616, 10.4.6 and 14.7)
                self.setHeader(b'Allow', b', '.join(allowedMethods))
                s = ('''Your browser approached me (at %(URI)s) with'''
                     ''' the method "%(method)s".  I only allow'''
                     ''' the method%(plural)s %(allowed)s here.''' % {
                         'URI': escape(nativeString(self.uri)),
                         'method': nativeString(self.method),
                         'plural': ((len(allowedMethods) > 1) and 's') or '',
                         'allowed': ', '.join(
                            [nativeString(x) for x in allowedMethods])
                     })
                epage = resource.ErrorPage(http.NOT_ALLOWED,
                                           "Method Not Allowed", s)
                body = epage.render(self)
            else:
                epage = resource.ErrorPage(
                    http.NOT_IMPLEMENTED, "Huh?",
                    "I don't know how to treat a %s request." %
                    (escape(self.method.decode("charmap")),))
                body = epage.render(self)
        # end except UnsupportedMethod

        if body == NOT_DONE_YET:
            return
        if not isinstance(body, bytes):
            body = resource.ErrorPage(
                http.INTERNAL_SERVER_ERROR,
                "Request did not return bytes",
                "Request: " + util._PRE(reflect.safe_repr(self)) + "<br />" +
                "Resource: " + util._PRE(reflect.safe_repr(resrc)) + "<br />" +
                "Value: " + util._PRE(reflect.safe_repr(body))).render(self)

        if self.method == b"HEAD":
            if len(body) > 0:
                # This is a Bad Thing (RFC 2616, 9.4)
                log.msg("Warning: HEAD request %s for resource %s is"
                        " returning a message body."
                        "  I think I'll eat it."
                        % (self, resrc))
                self.setHeader(b'content-length',
                               intToBytes(len(body)))
            self.write(b'')
        else:
            self.setHeader(b'content-length',
                           intToBytes(len(body)))
            self.write(body)
        self.finish()


    def processingFailed(self, reason):
        log.err(reason)
        if self.site.displayTracebacks:
            body = (b"<html><head><title>web.Server Traceback"
                    b" (most recent call last)</title></head>"
                    b"<body><b>web.Server Traceback"
                    b" (most recent call last):</b>\n\n" +
                    util.formatFailure(reason) +
                    b"\n\n</body></html>\n")
        else:
            body = (b"<html><head><title>Processing Failed"
                    b"</title></head><body>"
                    b"<b>Processing Failed</b></body></html>")

        self.setResponseCode(http.INTERNAL_SERVER_ERROR)
        self.setHeader(b'content-type', b"text/html")
        self.setHeader(b'content-length', intToBytes(len(body)))
        self.write(body)
        self.finish()
        return reason


    def view_write(self, issuer, data):
        """Remote version of write; same interface.
        """
        self.write(data)


    def view_finish(self, issuer):
        """Remote version of finish; same interface.
        """
        self.finish()


    def view_addCookie(self, issuer, k, v, **kwargs):
        """Remote version of addCookie; same interface.
        """
        self.addCookie(k, v, **kwargs)


    def view_setHeader(self, issuer, k, v):
        """Remote version of setHeader; same interface.
        """
        self.setHeader(k, v)


    def view_setLastModified(self, issuer, when):
        """Remote version of setLastModified; same interface.
        """
        self.setLastModified(when)


    def view_setETag(self, issuer, tag):
        """Remote version of setETag; same interface.
        """
        self.setETag(tag)


    def view_setResponseCode(self, issuer, code, message=None):
        """
        Remote version of setResponseCode; same interface.
        """
        self.setResponseCode(code, message)


    def view_registerProducer(self, issuer, producer, streaming):
        """Remote version of registerProducer; same interface.
        (requires a remote producer.)
        """
        self.registerProducer(_RemoteProducerWrapper(producer), streaming)


    def view_unregisterProducer(self, issuer):
        self.unregisterProducer()

    ### these calls remain local

    _secureSession = None
    _insecureSession = None

    @property
    def session(self):
        """
        If a session has already been created or looked up with
        L{Request.getSession}, this will return that object.  (This will always
        be the session that matches the security of the request; so if
        C{forceNotSecure} is used on a secure request, this will not return
        that session.)

        @return: the session attribute
        @rtype: L{Session} or L{None}
        """
        if self.isSecure():
            return self._secureSession
        else:
            return self._insecureSession


    def getSession(self, sessionInterface=None, forceNotSecure=False):
        """
        Check if there is a session cookie, and if not, create it.

        By default, the cookie with be secure for HTTPS requests and not secure
        for HTTP requests.  If for some reason you need access to the insecure
        cookie from a secure request you can set C{forceNotSecure = True}.

        @param forceNotSecure: Should we retrieve a session that will be
            transmitted over HTTP, even if this L{Request} was delivered over
            HTTPS?
        @type forceNotSecure: L{bool}
        """
        # Make sure we aren't creating a secure session on a non-secure page
        secure = self.isSecure() and not forceNotSecure

        if not secure:
            cookieString = b"TWISTED_SESSION"
            sessionAttribute = "_insecureSession"
        else:
            cookieString = b"TWISTED_SECURE_SESSION"
            sessionAttribute = "_secureSession"

        session = getattr(self, sessionAttribute)

        # Session management
        if not session:
            cookiename = b"_".join([cookieString] + self.sitepath)
            sessionCookie = self.getCookie(cookiename)
            if sessionCookie:
                try:
                    session = self.site.getSession(sessionCookie)
                except KeyError:
                    pass
            # if it still hasn't been set, fix it up.
            if not session:
                session = self.site.makeSession()
                self.addCookie(cookiename, session.uid, path=b"/",
                               secure=secure)

        session.touch()
        setattr(self, sessionAttribute, session)

        if sessionInterface:
            return session.getComponent(sessionInterface)

        return session


    def _prePathURL(self, prepath):
        port = self.getHost().port
        if self.isSecure():
            default = 443
        else:
            default = 80
        if port == default:
            hostport = ''
        else:
            hostport = ':%d' % port
        prefix = networkString('http%s://%s%s/' % (
            self.isSecure() and 's' or '',
            nativeString(self.getRequestHostname()),
            hostport))
        path = b'/'.join([quote(segment, safe=b'') for segment in prepath])
        return prefix + path


    def prePathURL(self):
        return self._prePathURL(self.prepath)


    def URLPath(self):
        from twisted.python import urlpath
        return urlpath.URLPath.fromRequest(self)


    def rememberRootURL(self):
        """
        Remember the currently-processed part of the URL for later
        recalling.
        """
        url = self._prePathURL(self.prepath[:-1])
        self.appRootURL = url


    def getRootURL(self):
        """
        Get a previously-remembered URL.
        """
        return self.appRootURL



@implementer(iweb._IRequestEncoderFactory)
class GzipEncoderFactory(object):
    """
    @cvar compressLevel: The compression level used by the compressor, default
        to 9 (highest).

    @since: 12.3
    """

    compressLevel = 9

    def encoderForRequest(self, request):
        """
        Check the headers if the client accepts gzip encoding, and encodes the
        request if so.
        """
        acceptHeaders = request.requestHeaders.getRawHeaders(
            'accept-encoding', [])
        supported = ','.join(acceptHeaders).split(',')
        if 'gzip' in supported:
            encoding = request.responseHeaders.getRawHeaders(
                'content-encoding')
            if encoding:
                encoding = '%s,gzip' % ','.join(encoding)
            else:
                encoding = 'gzip'

            request.responseHeaders.setRawHeaders('content-encoding',
                                                  [encoding])
            return _GzipEncoder(self.compressLevel, request)



@implementer(iweb._IRequestEncoder)
class _GzipEncoder(object):
    """
    An encoder which supports gzip.

    @ivar _zlibCompressor: The zlib compressor instance used to compress the
        stream.

    @ivar _request: A reference to the originating request.

    @since: 12.3
    """

    _zlibCompressor = None

    def __init__(self, compressLevel, request):
        self._zlibCompressor = zlib.compressobj(
            compressLevel, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
        self._request = request


    def encode(self, data):
        """
        Write to the request, automatically compressing data on the fly.
        """
        if not self._request.startedWriting:
            # Remove the content-length header, we can't honor it
            # because we compress on the fly.
            self._request.responseHeaders.removeHeader(b'content-length')
        return self._zlibCompressor.compress(data)


    def finish(self):
        """
        Finish handling the request request, flushing any data from the zlib
        buffer.
        """
        remain = self._zlibCompressor.flush()
        self._zlibCompressor = None
        return remain



class _RemoteProducerWrapper:
    def __init__(self, remote):
        self.resumeProducing = remote.remoteMethod("resumeProducing")
        self.pauseProducing = remote.remoteMethod("pauseProducing")
        self.stopProducing = remote.remoteMethod("stopProducing")



class Session(components.Componentized):
    """
    A user's session with a system.

    This utility class contains no functionality, but is used to
    represent a session.

    @ivar uid: A unique identifier for the session.
    @type uid: L{bytes}

    @ivar _reactor: An object providing L{IReactorTime} to use for scheduling
        expiration.
    @ivar sessionTimeout: timeout of a session, in seconds.
    """
    sessionTimeout = 900

    _expireCall = None

    def __init__(self, site, uid, reactor=None):
        """
        Initialize a session with a unique ID for that session.
        """
        components.Componentized.__init__(self)

        if reactor is None:
            from twisted.internet import reactor
        self._reactor = reactor

        self.site = site
        self.uid = uid
        self.expireCallbacks = []
        self.touch()
        self.sessionNamespaces = {}


    def startCheckingExpiration(self):
        """
        Start expiration tracking.

        @return: L{None}
        """
        self._expireCall = self._reactor.callLater(
            self.sessionTimeout, self.expire)


    def notifyOnExpire(self, callback):
        """
        Call this callback when the session expires or logs out.
        """
        self.expireCallbacks.append(callback)


    def expire(self):
        """
        Expire/logout of the session.
        """
        del self.site.sessions[self.uid]
        for c in self.expireCallbacks:
            c()
        self.expireCallbacks = []
        if self._expireCall and self._expireCall.active():
            self._expireCall.cancel()
            # Break reference cycle.
            self._expireCall = None


    def touch(self):
        """
        Notify session modification.
        """
        self.lastModified = self._reactor.seconds()
        if self._expireCall is not None:
            self._expireCall.reset(self.sessionTimeout)


version = networkString("TwistedWeb/%s" % (copyright.version,))



@implementer(interfaces.IProtocolNegotiationFactory)
class Site(http.HTTPFactory):
    """
    A web site: manage log, sessions, and resources.

    @ivar counter: increment value used for generating unique sessions ID.
    @ivar requestFactory: A factory which is called with (channel)
        and creates L{Request} instances. Default to L{Request}.
    @ivar displayTracebacks: if set, Twisted internal errors are displayed on
        rendered pages. Default to C{True}.
    @ivar sessionFactory: factory for sessions objects. Default to L{Session}.
    @ivar sessionCheckTime: Deprecated.  See L{Session.sessionTimeout} instead.
    """
    counter = 0
    requestFactory = Request
    displayTracebacks = True
    sessionFactory = Session
    sessionCheckTime = 1800
    _entropy = os.urandom

    def __init__(self, resource, requestFactory=None, *args, **kwargs):
        """
        @param resource: The root of the resource hierarchy.  All request
            traversal for requests received by this factory will begin at this
            resource.
        @type resource: L{IResource} provider
        @param requestFactory: Overwrite for default requestFactory.
        @type requestFactory: C{callable} or C{class}.

        @see: L{twisted.web.http.HTTPFactory.__init__}
        """
        http.HTTPFactory.__init__(self, *args, **kwargs)
        self.sessions = {}
        self.resource = resource
        if requestFactory is not None:
            self.requestFactory = requestFactory


    def _openLogFile(self, path):
        from twisted.python import logfile
        return logfile.LogFile(os.path.basename(path), os.path.dirname(path))


    def __getstate__(self):
        d = self.__dict__.copy()
        d['sessions'] = {}
        return d


    def _mkuid(self):
        """
        (internal) Generate an opaque, unique ID for a user's session.
        """
        self.counter = self.counter + 1
        return hexlify(self._entropy(32))


    def makeSession(self):
        """
        Generate a new Session instance, and store it for future reference.
        """
        uid = self._mkuid()
        session = self.sessions[uid] = self.sessionFactory(self, uid)
        session.startCheckingExpiration()
        return session


    def getSession(self, uid):
        """
        Get a previously generated session.

        @param uid: Unique ID of the session.
        @type uid: L{bytes}.

        @raise: L{KeyError} if the session is not found.
        """
        return self.sessions[uid]


    def buildProtocol(self, addr):
        """
        Generate a channel attached to this site.
        """
        channel = http.HTTPFactory.buildProtocol(self, addr)
        channel.requestFactory = self.requestFactory
        channel.site = self
        return channel

    isLeaf = 0

    def render(self, request):
        """
        Redirect because a Site is always a directory.
        """
        request.redirect(request.prePathURL() + b'/')
        request.finish()


    def getChildWithDefault(self, pathEl, request):
        """
        Emulate a resource's getChild method.
        """
        request.site = self
        return self.resource.getChildWithDefault(pathEl, request)


    def getResourceFor(self, request):
        """
        Get a resource for a request.

        This iterates through the resource hierarchy, calling
        getChildWithDefault on each resource it finds for a path element,
        stopping when it hits an element where isLeaf is true.
        """
        request.site = self
        # Sitepath is used to determine cookie names between distributed
        # servers and disconnected sites.
        request.sitepath = copy.copy(request.prepath)
        return resource.getChildForRequest(self.resource, request)

    # IProtocolNegotiationFactory
    def acceptableProtocols(self):
        """
        Protocols this server can speak.
        """
        baseProtocols = [b'http/1.1']

        if http.H2_ENABLED:
            baseProtocols.insert(0, b'h2')

        return baseProtocols

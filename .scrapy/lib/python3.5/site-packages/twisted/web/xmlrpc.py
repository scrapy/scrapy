# -*- test-case-name: twisted.web.test.test_xmlrpc -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A generic resource for publishing objects via XML-RPC.

Maintainer: Itamar Shtull-Trauring

@var Fault: See L{xmlrpclib.Fault}
@type Fault: L{xmlrpclib.Fault}
"""

from __future__ import division, absolute_import

from twisted.python.compat import _PY3, intToBytes, nativeString, urllib_parse
from twisted.python.compat import unicode

# System Imports
import base64
if _PY3:
    import xmlrpc.client as xmlrpclib
else:
    import xmlrpclib

# Sibling Imports
from twisted.web import resource, server, http
from twisted.internet import defer, protocol, reactor
from twisted.python import log, reflect, failure

# These are deprecated, use the class level definitions
NOT_FOUND = 8001
FAILURE = 8002


# Useful so people don't need to import xmlrpclib directly
Fault = xmlrpclib.Fault
Binary = xmlrpclib.Binary
Boolean = xmlrpclib.Boolean
DateTime = xmlrpclib.DateTime


def withRequest(f):
    """
    Decorator to cause the request to be passed as the first argument
    to the method.

    If an I{xmlrpc_} method is wrapped with C{withRequest}, the
    request object is passed as the first argument to that method.
    For example::

        @withRequest
        def xmlrpc_echo(self, request, s):
            return s

    @since: 10.2
    """
    f.withRequest = True
    return f



class NoSuchFunction(Fault):
    """
    There is no function by the given name.
    """


class Handler:
    """
    Handle a XML-RPC request and store the state for a request in progress.

    Override the run() method and return result using self.result,
    a Deferred.

    We require this class since we're not using threads, so we can't
    encapsulate state in a running function if we're going  to have
    to wait for results.

    For example, lets say we want to authenticate against twisted.cred,
    run a LDAP query and then pass its result to a database query, all
    as a result of a single XML-RPC command. We'd use a Handler instance
    to store the state of the running command.
    """

    def __init__(self, resource, *args):
        self.resource = resource # the XML-RPC resource we are connected to
        self.result = defer.Deferred()
        self.run(*args)

    def run(self, *args):
        # event driven equivalent of 'raise UnimplementedError'
        self.result.errback(
            NotImplementedError("Implement run() in subclasses"))


class XMLRPC(resource.Resource):
    """
    A resource that implements XML-RPC.

    You probably want to connect this to '/RPC2'.

    Methods published can return XML-RPC serializable results, Faults,
    Binary, Boolean, DateTime, Deferreds, or Handler instances.

    By default methods beginning with 'xmlrpc_' are published.

    Sub-handlers for prefixed methods (e.g., system.listMethods)
    can be added with putSubHandler. By default, prefixes are
    separated with a '.'. Override self.separator to change this.

    @ivar allowNone: Permit XML translating of Python constant None.
    @type allowNone: C{bool}

    @ivar useDateTime: Present C{datetime} values as C{datetime.datetime}
        objects?
    @type useDateTime: C{bool}
    """

    # Error codes for Twisted, if they conflict with yours then
    # modify them at runtime.
    NOT_FOUND = 8001
    FAILURE = 8002

    isLeaf = 1
    separator = '.'
    allowedMethods = (b'POST',)

    def __init__(self, allowNone=False, useDateTime=False):
        resource.Resource.__init__(self)
        self.subHandlers = {}
        self.allowNone = allowNone
        self.useDateTime = useDateTime


    def __setattr__(self, name, value):
        self.__dict__[name] = value


    def putSubHandler(self, prefix, handler):
        self.subHandlers[prefix] = handler

    def getSubHandler(self, prefix):
        return self.subHandlers.get(prefix, None)

    def getSubHandlerPrefixes(self):
        return list(self.subHandlers.keys())

    def render_POST(self, request):
        request.content.seek(0, 0)
        request.setHeader(b"content-type", b"text/xml; charset=utf-8")
        try:
            args, functionPath = xmlrpclib.loads(request.content.read(),
                use_datetime=self.useDateTime)
        except Exception as e:
            f = Fault(self.FAILURE, "Can't deserialize input: %s" % (e,))
            self._cbRender(f, request)
        else:
            try:
                function = self.lookupProcedure(functionPath)
            except Fault as f:
                self._cbRender(f, request)
            else:
                # Use this list to track whether the response has failed or not.
                # This will be used later on to decide if the result of the
                # Deferred should be written out and Request.finish called.
                responseFailed = []
                request.notifyFinish().addErrback(responseFailed.append)
                if getattr(function, 'withRequest', False):
                    d = defer.maybeDeferred(function, request, *args)
                else:
                    d = defer.maybeDeferred(function, *args)
                d.addErrback(self._ebRender)
                d.addCallback(self._cbRender, request, responseFailed)
        return server.NOT_DONE_YET


    def _cbRender(self, result, request, responseFailed=None):
        if responseFailed:
            return

        if isinstance(result, Handler):
            result = result.result
        if not isinstance(result, Fault):
            result = (result,)
        try:
            try:
                content = xmlrpclib.dumps(
                    result, methodresponse=True,
                    allow_none=self.allowNone)
            except Exception as e:
                f = Fault(self.FAILURE, "Can't serialize output: %s" % (e,))
                content = xmlrpclib.dumps(f, methodresponse=True,
                                          allow_none=self.allowNone)

            if isinstance(content, unicode):
                content = content.encode('utf8')
            request.setHeader(
                b"content-length", intToBytes(len(content)))
            request.write(content)
        except:
            log.err()
        request.finish()


    def _ebRender(self, failure):
        if isinstance(failure.value, Fault):
            return failure.value
        log.err(failure)
        return Fault(self.FAILURE, "error")


    def lookupProcedure(self, procedurePath):
        """
        Given a string naming a procedure, return a callable object for that
        procedure or raise NoSuchFunction.

        The returned object will be called, and should return the result of the
        procedure, a Deferred, or a Fault instance.

        Override in subclasses if you want your own policy.  The base
        implementation that given C{'foo'}, C{self.xmlrpc_foo} will be returned.
        If C{procedurePath} contains C{self.separator}, the sub-handler for the
        initial prefix is used to search for the remaining path.

        If you override C{lookupProcedure}, you may also want to override
        C{listProcedures} to accurately report the procedures supported by your
        resource, so that clients using the I{system.listMethods} procedure
        receive accurate results.

        @since: 11.1
        """
        if procedurePath.find(self.separator) != -1:
            prefix, procedurePath = procedurePath.split(self.separator, 1)
            handler = self.getSubHandler(prefix)
            if handler is None:
                raise NoSuchFunction(self.NOT_FOUND,
                    "no such subHandler %s" % prefix)
            return handler.lookupProcedure(procedurePath)

        f = getattr(self, "xmlrpc_%s" % procedurePath, None)
        if not f:
            raise NoSuchFunction(self.NOT_FOUND,
                "procedure %s not found" % procedurePath)
        elif not callable(f):
            raise NoSuchFunction(self.NOT_FOUND,
                "procedure %s not callable" % procedurePath)
        else:
            return f

    def listProcedures(self):
        """
        Return a list of the names of all xmlrpc procedures.

        @since: 11.1
        """
        return reflect.prefixedMethodNames(self.__class__, 'xmlrpc_')


class XMLRPCIntrospection(XMLRPC):
    """
    Implement the XML-RPC Introspection API.

    By default, the methodHelp method returns the 'help' method attribute,
    if it exists, otherwise the __doc__ method attribute, if it exists,
    otherwise the empty string.

    To enable the methodSignature method, add a 'signature' method attribute
    containing a list of lists. See methodSignature's documentation for the
    format. Note the type strings should be XML-RPC types, not Python types.
    """

    def __init__(self, parent):
        """
        Implement Introspection support for an XMLRPC server.

        @param parent: the XMLRPC server to add Introspection support to.
        @type parent: L{XMLRPC}
        """
        XMLRPC.__init__(self)
        self._xmlrpc_parent = parent

    def xmlrpc_listMethods(self):
        """
        Return a list of the method names implemented by this server.
        """
        functions = []
        todo = [(self._xmlrpc_parent, '')]
        while todo:
            obj, prefix = todo.pop(0)
            functions.extend([prefix + name for name in obj.listProcedures()])
            todo.extend([ (obj.getSubHandler(name),
                           prefix + name + obj.separator)
                          for name in obj.getSubHandlerPrefixes() ])
        return functions

    xmlrpc_listMethods.signature = [['array']]

    def xmlrpc_methodHelp(self, method):
        """
        Return a documentation string describing the use of the given method.
        """
        method = self._xmlrpc_parent.lookupProcedure(method)
        return (getattr(method, 'help', None)
                or getattr(method, '__doc__', None) or '')

    xmlrpc_methodHelp.signature = [['string', 'string']]

    def xmlrpc_methodSignature(self, method):
        """
        Return a list of type signatures.

        Each type signature is a list of the form [rtype, type1, type2, ...]
        where rtype is the return type and typeN is the type of the Nth
        argument. If no signature information is available, the empty
        string is returned.
        """
        method = self._xmlrpc_parent.lookupProcedure(method)
        return getattr(method, 'signature', None) or ''

    xmlrpc_methodSignature.signature = [['array', 'string'],
                                        ['string', 'string']]


def addIntrospection(xmlrpc):
    """
    Add Introspection support to an XMLRPC server.

    @param parent: the XMLRPC server to add Introspection support to.
    @type parent: L{XMLRPC}
    """
    xmlrpc.putSubHandler('system', XMLRPCIntrospection(xmlrpc))


class QueryProtocol(http.HTTPClient):
    def connectionMade(self):
        self._response = None
        self.sendCommand(b'POST', self.factory.path)
        self.sendHeader(b'User-Agent', b'Twisted/XMLRPClib')
        self.sendHeader(b'Host', self.factory.host)
        self.sendHeader(b'Content-type', b'text/xml; charset=utf-8')
        payload = self.factory.payload
        self.sendHeader(b'Content-length', intToBytes(len(payload)))

        if self.factory.user:
            auth = b':'.join([self.factory.user, self.factory.password])
            authHeader = b''.join([b'Basic ', base64.b64encode(auth)])
            self.sendHeader(b'Authorization', authHeader)
        self.endHeaders()
        self.transport.write(payload)

    def handleStatus(self, version, status, message):
        if status != b'200':
            self.factory.badStatus(status, message)

    def handleResponse(self, contents):
        """
        Handle the XML-RPC response received from the server.

        Specifically, disconnect from the server and store the XML-RPC
        response so that it can be properly handled when the disconnect is
        finished.
        """
        self.transport.loseConnection()
        self._response = contents

    def connectionLost(self, reason):
        """
        The connection to the server has been lost.

        If we have a full response from the server, then parse it and fired a
        Deferred with the return value or C{Fault} that the server gave us.
        """
        http.HTTPClient.connectionLost(self, reason)
        if self._response is not None:
            response, self._response = self._response, None
            self.factory.parseResponse(response)


payloadTemplate = """<?xml version="1.0"?>
<methodCall>
<methodName>%s</methodName>
%s
</methodCall>
"""


class _QueryFactory(protocol.ClientFactory):
    """
    XML-RPC Client Factory

    @ivar path: The path portion of the URL to which to post method calls.
    @type path: L{bytes}

    @ivar host: The value to use for the Host HTTP header.
    @type host: L{bytes}

    @ivar user: The username with which to authenticate with the server
        when making calls.
    @type user: L{bytes} or L{None}

    @ivar password: The password with which to authenticate with the server
        when making calls.
    @type password: L{bytes} or L{None}

    @ivar useDateTime: Accept datetime values as datetime.datetime objects.
        also passed to the underlying xmlrpclib implementation.  Defaults to
        C{False}.
    @type useDateTime: C{bool}
    """

    deferred = None
    protocol = QueryProtocol

    def __init__(self, path, host, method, user=None, password=None,
                 allowNone=False, args=(), canceller=None, useDateTime=False):
        """
        @param method: The name of the method to call.
        @type method: C{str}

        @param allowNone: allow the use of None values in parameters. It's
            passed to the underlying xmlrpclib implementation. Defaults to
            C{False}.
        @type allowNone: C{bool} or L{None}

        @param args: the arguments to pass to the method.
        @type args: C{tuple}

        @param canceller: A 1-argument callable passed to the deferred as the
            canceller callback.
        @type canceller: callable or L{None}
        """
        self.path, self.host = path, host
        self.user, self.password = user, password
        self.payload = payloadTemplate % (method,
            xmlrpclib.dumps(args, allow_none=allowNone))
        if isinstance(self.payload, unicode):
            self.payload = self.payload.encode('utf8')
        self.deferred = defer.Deferred(canceller)
        self.useDateTime = useDateTime

    def parseResponse(self, contents):
        if not self.deferred:
            return
        try:
            response = xmlrpclib.loads(contents,
                use_datetime=self.useDateTime)[0][0]
        except:
            deferred, self.deferred = self.deferred, None
            deferred.errback(failure.Failure())
        else:
            deferred, self.deferred = self.deferred, None
            deferred.callback(response)

    def clientConnectionLost(self, _, reason):
        if self.deferred is not None:
            deferred, self.deferred = self.deferred, None
            deferred.errback(reason)

    clientConnectionFailed = clientConnectionLost

    def badStatus(self, status, message):
        deferred, self.deferred = self.deferred, None
        deferred.errback(ValueError(status, message))



class Proxy:
    """
    A Proxy for making remote XML-RPC calls.

    Pass the URL of the remote XML-RPC server to the constructor.

    Use C{proxy.callRemote('foobar', *args)} to call remote method
    'foobar' with *args.

    @ivar user: The username with which to authenticate with the server
        when making calls.  If specified, overrides any username information
        embedded in C{url}.  If not specified, a value may be taken from
        C{url} if present.
    @type user: L{bytes} or L{None}

    @ivar password: The password with which to authenticate with the server
        when making calls.  If specified, overrides any password information
        embedded in C{url}.  If not specified, a value may be taken from
        C{url} if present.
    @type password: L{bytes} or L{None}

    @ivar allowNone: allow the use of None values in parameters. It's
        passed to the underlying L{xmlrpclib} implementation. Defaults to
        C{False}.
    @type allowNone: C{bool} or L{None}

    @ivar useDateTime: Accept datetime values as datetime.datetime objects.
        also passed to the underlying L{xmlrpclib} implementation. Defaults to
        C{False}.
    @type useDateTime: C{bool}

    @ivar connectTimeout: Number of seconds to wait before assuming the
        connection has failed.
    @type connectTimeout: C{float}

    @ivar _reactor: The reactor used to create connections.
    @type _reactor: Object providing L{twisted.internet.interfaces.IReactorTCP}

    @ivar queryFactory: Object returning a factory for XML-RPC protocol. Mainly
        useful for tests.
    """
    queryFactory = _QueryFactory

    def __init__(self, url, user=None, password=None, allowNone=False,
                 useDateTime=False, connectTimeout=30.0, reactor=reactor):
        """
        @param url: The URL to which to post method calls.  Calls will be made
            over SSL if the scheme is HTTPS.  If netloc contains username or
            password information, these will be used to authenticate, as long as
            the C{user} and C{password} arguments are not specified.
        @type url: L{bytes}

        """
        scheme, netloc, path, params, query, fragment = urllib_parse.urlparse(
            url)
        netlocParts = netloc.split(b'@')
        if len(netlocParts) == 2:
            userpass = netlocParts.pop(0).split(b':')
            self.user = userpass.pop(0)
            try:
                self.password = userpass.pop(0)
            except:
                self.password = None
        else:
            self.user = self.password = None
        hostport = netlocParts[0].split(b':')
        self.host = hostport.pop(0)
        try:
            self.port = int(hostport.pop(0))
        except:
            self.port = None
        self.path = path
        if self.path in [b'', None]:
            self.path = b'/'
        self.secure = (scheme == b'https')
        if user is not None:
            self.user = user
        if password is not None:
            self.password = password
        self.allowNone = allowNone
        self.useDateTime = useDateTime
        self.connectTimeout = connectTimeout
        self._reactor = reactor


    def callRemote(self, method, *args):
        """
        Call remote XML-RPC C{method} with given arguments.

        @return: a L{defer.Deferred} that will fire with the method response,
            or a failure if the method failed. Generally, the failure type will
            be L{Fault}, but you can also have an C{IndexError} on some buggy
            servers giving empty responses.

            If the deferred is cancelled before the request completes, the
            connection is closed and the deferred will fire with a
            L{defer.CancelledError}.
        """
        def cancel(d):
            factory.deferred = None
            connector.disconnect()
        factory = self.queryFactory(
            self.path, self.host, method, self.user,
            self.password, self.allowNone, args, cancel, self.useDateTime)

        if self.secure:
            from twisted.internet import ssl
            connector = self._reactor.connectSSL(
                nativeString(self.host), self.port or 443,
                factory, ssl.ClientContextFactory(),
                timeout=self.connectTimeout)
        else:
            connector = self._reactor.connectTCP(
                nativeString(self.host), self.port or 80, factory,
                timeout=self.connectTimeout)
        return factory.deferred


__all__ = [
    "XMLRPC", "Handler", "NoSuchFunction", "Proxy",

    "Fault", "Binary", "Boolean", "DateTime"]

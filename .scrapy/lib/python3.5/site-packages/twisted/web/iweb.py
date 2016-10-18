# -*- test-case-name: twisted.web.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Interface definitions for L{twisted.web}.

@var UNKNOWN_LENGTH: An opaque object which may be used as the value of
    L{IBodyProducer.length} to indicate that the length of the entity
    body is not known in advance.
"""

from zope.interface import Interface, Attribute

from twisted.internet.interfaces import IPushProducer
from twisted.cred.credentials import IUsernameDigestHash


class IRequest(Interface):
    """
    An HTTP request.

    @since: 9.0
    """

    method = Attribute("A C{str} giving the HTTP method that was used.")
    uri = Attribute(
        "A C{str} giving the full encoded URI which was requested (including "
        "query arguments).")
    path = Attribute(
        "A C{str} giving the encoded query path of the request URI.")
    args = Attribute(
        "A mapping of decoded query argument names as C{str} to "
        "corresponding query argument values as C{list}s of C{str}.  "
        "For example, for a URI with C{'foo=bar&foo=baz&quux=spam'} "
        "for its query part, C{args} will be C{{'foo': ['bar', 'baz'], "
        "'quux': ['spam']}}.")

    requestHeaders = Attribute(
        "A L{http_headers.Headers} instance giving all received HTTP request "
        "headers.")

    content = Attribute(
        "A file-like object giving the request body.  This may be a file on "
        "disk, a C{StringIO}, or some other type.  The implementation is free "
        "to decide on a per-request basis.")

    responseHeaders = Attribute(
        "A L{http_headers.Headers} instance holding all HTTP response "
        "headers to be sent.")

    def getHeader(key):
        """
        Get an HTTP request header.

        @type key: C{str}
        @param key: The name of the header to get the value of.

        @rtype: C{str} or L{None}
        @return: The value of the specified header, or L{None} if that header
            was not present in the request.
        """


    def getCookie(key):
        """
        Get a cookie that was sent from the network.
        """


    def getAllHeaders():
        """
        Return dictionary mapping the names of all received headers to the last
        value received for each.

        Since this method does not return all header information,
        C{requestHeaders.getAllRawHeaders()} may be preferred.
        """


    def getRequestHostname():
        """
        Get the hostname that the user passed in to the request.

        This will either use the Host: header (if it is available) or the
        host we are listening on if the header is unavailable.

        @returns: the requested hostname
        @rtype: C{str}
        """


    def getHost():
        """
        Get my originally requesting transport's host.

        @return: An L{IAddress<twisted.internet.interfaces.IAddress>}.
        """


    def getClientIP():
        """
        Return the IP address of the client who submitted this request.

        @returns: the client IP address or L{None} if the request was submitted
            over a transport where IP addresses do not make sense.
        @rtype: L{str} or L{None}
        """


    def getClient():
        """
        Return the hostname of the IP address of the client who submitted this
        request, if possible.

        This method is B{deprecated}.  See L{getClientIP} instead.

        @rtype: L{None} or L{str}
        @return: The canonical hostname of the client, as determined by
            performing a name lookup on the IP address of the client.
        """


    def getUser():
        """
        Return the HTTP user sent with this request, if any.

        If no user was supplied, return the empty string.

        @returns: the HTTP user, if any
        @rtype: C{str}
        """


    def getPassword():
        """
        Return the HTTP password sent with this request, if any.

        If no password was supplied, return the empty string.

        @returns: the HTTP password, if any
        @rtype: C{str}
        """


    def isSecure():
        """
        Return True if this request is using a secure transport.

        Normally this method returns True if this request's HTTPChannel
        instance is using a transport that implements ISSLTransport.

        This will also return True if setHost() has been called
        with ssl=True.

        @returns: True if this request is secure
        @rtype: C{bool}
        """


    def getSession(sessionInterface=None):
        """
        Look up the session associated with this request or create a new one if
        there is not one.

        @return: The L{Session} instance identified by the session cookie in
            the request, or the C{sessionInterface} component of that session
            if C{sessionInterface} is specified.
        """


    def URLPath():
        """
        @return: A L{URLPath} instance which identifies the URL for which this
            request is.
        """


    def prePathURL():
        """
        @return: At any time during resource traversal, a L{str} giving an
            absolute URL to the most nested resource which has yet been
            reached.
        """


    def rememberRootURL():
        """
        Remember the currently-processed part of the URL for later
        recalling.
        """


    def getRootURL():
        """
        Get a previously-remembered URL.
        """


    # Methods for outgoing response
    def finish():
        """
        Indicate that the response to this request is complete.
        """


    def write(data):
        """
        Write some data to the body of the response to this request.  Response
        headers are written the first time this method is called, after which
        new response headers may not be added.
        """


    def addCookie(k, v, expires=None, domain=None, path=None, max_age=None, comment=None, secure=None):
        """
        Set an outgoing HTTP cookie.

        In general, you should consider using sessions instead of cookies, see
        L{twisted.web.server.Request.getSession} and the
        L{twisted.web.server.Session} class for details.
        """


    def setResponseCode(code, message=None):
        """
        Set the HTTP response code.
        """


    def setHeader(k, v):
        """
        Set an HTTP response header.  Overrides any previously set values for
        this header.

        @type name: C{str}
        @param name: The name of the header for which to set the value.

        @type value: C{str}
        @param value: The value to set for the named header.
        """


    def redirect(url):
        """
        Utility function that does a redirect.

        The request should have finish() called after this.
        """


    def setLastModified(when):
        """
        Set the C{Last-Modified} time for the response to this request.

        If I am called more than once, I ignore attempts to set Last-Modified
        earlier, only replacing the Last-Modified time if it is to a later
        value.

        If I am a conditional request, I may modify my response code to
        L{NOT_MODIFIED<http.NOT_MODIFIED>} if appropriate for the time given.

        @param when: The last time the resource being returned was modified, in
            seconds since the epoch.
        @type when: L{int}, L{long} or L{float}

        @return: If I am a C{If-Modified-Since} conditional request and the time
            given is not newer than the condition, I return
            L{CACHED<http.CACHED>} to indicate that you should write no body.
            Otherwise, I return a false value.
        """


    def setETag(etag):
        """
        Set an C{entity tag} for the outgoing response.

        That's "entity tag" as in the HTTP/1.1 I{ETag} header, "used for
        comparing two or more entities from the same requested resource."

        If I am a conditional request, I may modify my response code to
        L{NOT_MODIFIED<http.NOT_MODIFIED>} or
        L{PRECONDITION_FAILED<http.PRECONDITION_FAILED>}, if appropriate for the
        tag given.

        @param etag: The entity tag for the resource being returned.
        @type etag: C{str}

        @return: If I am a C{If-None-Match} conditional request and the tag
            matches one in the request, I return L{CACHED<http.CACHED>} to
            indicate that you should write no body.  Otherwise, I return a
            false value.
        """


    def setHost(host, port, ssl=0):
        """
        Change the host and port the request thinks it's using.

        This method is useful for working with reverse HTTP proxies (e.g.  both
        Squid and Apache's mod_proxy can do this), when the address the HTTP
        client is using is different than the one we're listening on.

        For example, Apache may be listening on https://www.example.com, and
        then forwarding requests to http://localhost:8080, but we don't want
        HTML produced by Twisted to say 'http://localhost:8080', they should
        say 'https://www.example.com', so we do::

           request.setHost('www.example.com', 443, ssl=1)
        """



class INonQueuedRequestFactory(Interface):
    """
    A factory of L{IRequest} objects that does not take a ``queued`` parameter.
    """
    def __call__(channel):
        """
        Create an L{IRequest} that is operating on the given channel. There
        must only be one L{IRequest} object processing at any given time on a
        channel.

        @param channel: A L{twisted.web.http.HTTPChannel} object.
        @type channel: L{twisted.web.http.HTTPChannel}

        @return: A request object.
        @rtype: L{IRequest}
        """



class IAccessLogFormatter(Interface):
    """
    An object which can represent an HTTP request as a line of text for
    inclusion in an access log file.
    """
    def __call__(timestamp, request):
        """
        Generate a line for the access log.

        @param timestamp: The time at which the request was completed in the
            standard format for access logs.
        @type timestamp: L{unicode}

        @param request: The request object about which to log.
        @type request: L{twisted.web.server.Request}

        @return: One line describing the request without a trailing newline.
        @rtype: L{unicode}
        """



class ICredentialFactory(Interface):
    """
    A credential factory defines a way to generate a particular kind of
    authentication challenge and a way to interpret the responses to these
    challenges.  It creates
    L{ICredentials<twisted.cred.credentials.ICredentials>} providers from
    responses.  These objects will be used with L{twisted.cred} to authenticate
    an authorize requests.
    """
    scheme = Attribute(
        "A C{str} giving the name of the authentication scheme with which "
        "this factory is associated.  For example, C{'basic'} or C{'digest'}.")


    def getChallenge(request):
        """
        Generate a new challenge to be sent to a client.

        @type peer: L{twisted.web.http.Request}
        @param peer: The request the response to which this challenge will be
            included.

        @rtype: C{dict}
        @return: A mapping from C{str} challenge fields to associated C{str}
            values.
        """


    def decode(response, request):
        """
        Create a credentials object from the given response.

        @type response: C{str}
        @param response: scheme specific response string

        @type request: L{twisted.web.http.Request}
        @param request: The request being processed (from which the response
            was taken).

        @raise twisted.cred.error.LoginFailed: If the response is invalid.

        @rtype: L{twisted.cred.credentials.ICredentials} provider
        @return: The credentials represented by the given response.
        """



class IBodyProducer(IPushProducer):
    """
    Objects which provide L{IBodyProducer} write bytes to an object which
    provides L{IConsumer<twisted.internet.interfaces.IConsumer>} by calling its
    C{write} method repeatedly.

    L{IBodyProducer} providers may start producing as soon as they have an
    L{IConsumer<twisted.internet.interfaces.IConsumer>} provider.  That is, they
    should not wait for a C{resumeProducing} call to begin writing data.

    L{IConsumer.unregisterProducer<twisted.internet.interfaces.IConsumer.unregisterProducer>}
    must not be called.  Instead, the
    L{Deferred<twisted.internet.defer.Deferred>} returned from C{startProducing}
    must be fired when all bytes have been written.

    L{IConsumer.write<twisted.internet.interfaces.IConsumer.write>} may
    synchronously invoke any of C{pauseProducing}, C{resumeProducing}, or
    C{stopProducing}.  These methods must be implemented with this in mind.

    @since: 9.0
    """

    # Despite the restrictions above and the additional requirements of
    # stopProducing documented below, this interface still needs to be an
    # IPushProducer subclass.  Providers of it will be passed to IConsumer
    # providers which only know about IPushProducer and IPullProducer, not
    # about this interface.  This interface needs to remain close enough to one
    # of those interfaces for consumers to work with it.

    length = Attribute(
        """
        C{length} is a C{int} indicating how many bytes in total this
        L{IBodyProducer} will write to the consumer or L{UNKNOWN_LENGTH}
        if this is not known in advance.
        """)

    def startProducing(consumer):
        """
        Start producing to the given
        L{IConsumer<twisted.internet.interfaces.IConsumer>} provider.

        @return: A L{Deferred<twisted.internet.defer.Deferred>} which fires with
            L{None} when all bytes have been produced or with a
            L{Failure<twisted.python.failure.Failure>} if there is any problem
            before all bytes have been produced.
        """


    def stopProducing():
        """
        In addition to the standard behavior of
        L{IProducer.stopProducing<twisted.internet.interfaces.IProducer.stopProducing>}
        (stop producing data), make sure the
        L{Deferred<twisted.internet.defer.Deferred>} returned by
        C{startProducing} is never fired.
        """



class IRenderable(Interface):
    """
    An L{IRenderable} is an object that may be rendered by the
    L{twisted.web.template} templating system.
    """

    def lookupRenderMethod(name):
        """
        Look up and return the render method associated with the given name.

        @type name: C{str}
        @param name: The value of a render directive encountered in the
            document returned by a call to L{IRenderable.render}.

        @return: A two-argument callable which will be invoked with the request
            being responded to and the tag object on which the render directive
            was encountered.
        """


    def render(request):
        """
        Get the document for this L{IRenderable}.

        @type request: L{IRequest} provider or L{None}
        @param request: The request in response to which this method is being
            invoked.

        @return: An object which can be flattened.
        """



class ITemplateLoader(Interface):
    """
    A loader for templates; something usable as a value for
    L{twisted.web.template.Element}'s C{loader} attribute.
    """

    def load():
        """
        Load a template suitable for rendering.

        @return: a C{list} of C{list}s, C{unicode} objects, C{Element}s and
            other L{IRenderable} providers.
        """



class IResponse(Interface):
    """
    An object representing an HTTP response received from an HTTP server.

    @since: 11.1
    """

    version = Attribute(
        "A three-tuple describing the protocol and protocol version "
        "of the response.  The first element is of type C{str}, the second "
        "and third are of type C{int}.  For example, C{('HTTP', 1, 1)}.")


    code = Attribute("The HTTP status code of this response, as a C{int}.")


    phrase = Attribute(
        "The HTTP reason phrase of this response, as a C{str}.")


    headers = Attribute("The HTTP response L{Headers} of this response.")


    length = Attribute(
        "The C{int} number of bytes expected to be in the body of this "
        "response or L{UNKNOWN_LENGTH} if the server did not indicate how "
        "many bytes to expect.  For I{HEAD} responses, this will be 0; if "
        "the response includes a I{Content-Length} header, it will be "
        "available in C{headers}.")


    request = Attribute(
        "The L{IClientRequest} that resulted in this response.")


    previousResponse = Attribute(
        "The previous L{IResponse} from a redirect, or L{None} if there was no "
        "previous response. This can be used to walk the response or request "
        "history for redirections.")


    def deliverBody(protocol):
        """
        Register an L{IProtocol<twisted.internet.interfaces.IProtocol>} provider
        to receive the response body.

        The protocol will be connected to a transport which provides
        L{IPushProducer}.  The protocol's C{connectionLost} method will be
        called with:

            - ResponseDone, which indicates that all bytes from the response
              have been successfully delivered.

            - PotentialDataLoss, which indicates that it cannot be determined
              if the entire response body has been delivered.  This only occurs
              when making requests to HTTP servers which do not set
              I{Content-Length} or a I{Transfer-Encoding} in the response.

            - ResponseFailed, which indicates that some bytes from the response
              were lost.  The C{reasons} attribute of the exception may provide
              more specific indications as to why.
        """


    def setPreviousResponse(response):
        """
        Set the reference to the previous L{IResponse}.

        The value of the previous response can be read via
        L{IResponse.previousResponse}.
        """



class _IRequestEncoder(Interface):
    """
    An object encoding data passed to L{IRequest.write}, for example for
    compression purpose.

    @since: 12.3
    """

    def encode(data):
        """
        Encode the data given and return the result.

        @param data: The content to encode.
        @type data: C{str}

        @return: The encoded data.
        @rtype: C{str}
        """


    def finish():
        """
        Callback called when the request is closing.

        @return: If necessary, the pending data accumulated from previous
            C{encode} calls.
        @rtype: C{str}
        """



class _IRequestEncoderFactory(Interface):
    """
    A factory for returing L{_IRequestEncoder} instances.

    @since: 12.3
    """

    def encoderForRequest(request):
        """
        If applicable, returns a L{_IRequestEncoder} instance which will encode
        the request.
        """



class IClientRequest(Interface):
    """
    An object representing an HTTP request to make to an HTTP server.

    @since: 13.1
    """
    method = Attribute(
        "The HTTP method for this request, as L{bytes}. For example: "
        "C{b'GET'}, C{b'HEAD'}, C{b'POST'}, etc.")


    absoluteURI = Attribute(
        "The absolute URI of the requested resource, as L{bytes}; or L{None} "
        "if the absolute URI cannot be determined.")


    headers = Attribute(
        "Headers to be sent to the server, as "
        "a L{twisted.web.http_headers.Headers} instance.")



class IAgent(Interface):
    """
    An agent makes HTTP requests.

    The way in which requests are issued is left up to each implementation.
    Some may issue them directly to the server indicated by the net location
    portion of the request URL.  Others may use a proxy specified by system
    configuration.

    Processing of responses is also left very widely specified.  An
    implementation may perform no special handling of responses, or it may
    implement redirect following or content negotiation, it may implement a
    cookie store or automatically respond to authentication challenges.  It may
    implement many other unforeseen behaviors as well.

    It is also intended that L{IAgent} implementations be composable.  An
    implementation which provides cookie handling features should re-use an
    implementation that provides connection pooling and this combination could
    be used by an implementation which adds content negotiation functionality.
    Some implementations will be completely self-contained, such as those which
    actually perform the network operations to send and receive requests, but
    most or all other implementations should implement a small number of new
    features (perhaps one new feature) and delegate the rest of the
    request/response machinery to another implementation.

    This allows for great flexibility in the behavior an L{IAgent} will
    provide.  For example, an L{IAgent} with web browser-like behavior could be
    obtained by combining a number of (hypothetical) implementations::

        baseAgent = Agent(reactor)
        redirect = BrowserLikeRedirectAgent(baseAgent, limit=10)
        authenticate = AuthenticateAgent(
            redirect, [diskStore.credentials, GtkAuthInterface()])
        cookie = CookieAgent(authenticate, diskStore.cookie)
        decode = ContentDecoderAgent(cookie, [(b"gzip", GzipDecoder())])
        cache = CacheAgent(decode, diskStore.cache)

        doSomeRequests(cache)
    """
    def request(method, uri, headers=None, bodyProducer=None):
        """
        Request the resource at the given location.

        @param method: The request method to use, such as C{"GET"}, C{"HEAD"},
            C{"PUT"}, C{"POST"}, etc.
        @type method: L{bytes}

        @param uri: The location of the resource to request.  This should be an
            absolute URI but some implementations may support relative URIs
            (with absolute or relative paths).  I{HTTP} and I{HTTPS} are the
            schemes most likely to be supported but others may be as well.
        @type uri: L{bytes}

        @param headers: The headers to send with the request (or L{None} to
            send no extra headers).  An implementation may add its own headers
            to this (for example for client identification or content
            negotiation).
        @type headers: L{Headers} or L{None}

        @param bodyProducer: An object which can generate bytes to make up the
            body of this request (for example, the properly encoded contents of
            a file for a file upload).  Or, L{None} if the request is to have
            no body.
        @type bodyProducer: L{IBodyProducer} provider

        @return: A L{Deferred} that fires with an L{IResponse} provider when
            the header of the response has been received (regardless of the
            response status code) or with a L{Failure} if there is any problem
            which prevents that response from being received (including
            problems that prevent the request from being sent).
        @rtype: L{Deferred}
        """


class IPolicyForHTTPS(Interface):
    """
    An L{IPolicyForHTTPS} provides a policy for verifying the certificates of
    HTTPS connections, in the form of a L{client connection creator
    <twisted.internet.interfaces.IOpenSSLClientConnectionCreator>} per network
    location.

    @since: 14.0
    """

    def creatorForNetloc(hostname, port):
        """
        Create a L{client connection creator
        <twisted.internet.interfaces.IOpenSSLClientConnectionCreator>}
        appropriate for the given URL "netloc"; i.e. hostname and port number
        pair.

        @param hostname: The name of the requested remote host.
        @type hostname: L{bytes}

        @param port: The number of the requested remote port.
        @type port: L{int}

        @return: A client connection creator expressing the security
            requirements for the given remote host.
        @rtype: L{client connection creator
            <twisted.internet.interfaces.IOpenSSLClientConnectionCreator>}
        """



class IAgentEndpointFactory(Interface):
    """
    An L{IAgentEndpointFactory} provides a way of constructing an endpoint
    used for outgoing Agent requests. This is useful in the case of needing to
    proxy outgoing connections, or to otherwise vary the transport used.

    @since: 15.0
    """

    def endpointForURI(uri):
        """
        Construct and return an L{IStreamClientEndpoint} for the outgoing
        request's connection.

        @param uri: The URI of the request.
        @type uri: L{twisted.web.client.URI}

        @return: An endpoint which will have its C{connect} method called to
            issue the request.
        @rtype: an L{IStreamClientEndpoint} provider

        @raises twisted.internet.error.SchemeNotSupported: If the given
            URI's scheme cannot be handled by this factory.
        """



UNKNOWN_LENGTH = u"twisted.web.iweb.UNKNOWN_LENGTH"

__all__ = [
    "IUsernameDigestHash", "ICredentialFactory", "IRequest",
    "IBodyProducer", "IRenderable", "IResponse", "_IRequestEncoder",
    "_IRequestEncoderFactory", "IClientRequest",

    "UNKNOWN_LENGTH"]

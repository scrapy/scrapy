# -*- test-case-name: twisted.words.test.test_jabberclient -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


from twisted.words.protocols.jabber import error, sasl, xmlstream
from twisted.words.protocols.jabber.jid import JID
from twisted.words.xish import domish, utility, xpath

NS_XMPP_STREAMS = "urn:ietf:params:xml:ns:xmpp-streams"
NS_XMPP_BIND = "urn:ietf:params:xml:ns:xmpp-bind"
NS_XMPP_SESSION = "urn:ietf:params:xml:ns:xmpp-session"
NS_IQ_AUTH_FEATURE = "http://jabber.org/features/iq-auth"

DigestAuthQry = xpath.internQuery("/iq/query/digest")
PlaintextAuthQry = xpath.internQuery("/iq/query/password")


def basicClientFactory(jid, secret):
    a = BasicAuthenticator(jid, secret)
    return xmlstream.XmlStreamFactory(a)


class IQ(domish.Element):
    """
    Wrapper for a Info/Query packet.

    This provides the necessary functionality to send IQs and get notified when
    a result comes back. It's a subclass from L{domish.Element}, so you can use
    the standard DOM manipulation calls to add data to the outbound request.

    @type callbacks: L{utility.CallbackList}
    @cvar callbacks: Callback list to be notified when response comes back

    """

    def __init__(self, xmlstream, type="set"):
        """
        @type xmlstream: L{xmlstream.XmlStream}
        @param xmlstream: XmlStream to use for transmission of this IQ

        @type type: C{str}
        @param type: IQ type identifier ('get' or 'set')
        """

        domish.Element.__init__(self, ("jabber:client", "iq"))
        self.addUniqueId()
        self["type"] = type
        self._xmlstream = xmlstream
        self.callbacks = utility.CallbackList()

    def addCallback(self, fn, *args, **kwargs):
        """
        Register a callback for notification when the IQ result is available.
        """

        self.callbacks.addCallback(True, fn, *args, **kwargs)

    def send(self, to=None):
        """
        Call this method to send this IQ request via the associated XmlStream.

        @param to: Jabber ID of the entity to send the request to
        @type to: C{str}

        @returns: Callback list for this IQ. Any callbacks added to this list
                  will be fired when the result comes back.
        """
        if to != None:
            self["to"] = to
        self._xmlstream.addOnetimeObserver(
            "/iq[@id='%s']" % self["id"], self._resultEvent
        )
        self._xmlstream.send(self)

    def _resultEvent(self, iq):
        self.callbacks.callback(iq)
        self.callbacks = None


class IQAuthInitializer:
    """
    Non-SASL Authentication initializer for the initiating entity.

    This protocol is defined in
    U{JEP-0078<http://www.jabber.org/jeps/jep-0078.html>} and mainly serves for
    compatibility with pre-XMPP-1.0 server implementations.

    @cvar INVALID_USER_EVENT: Token to signal that authentication failed, due
        to invalid username.
    @type INVALID_USER_EVENT: L{str}

    @cvar AUTH_FAILED_EVENT: Token to signal that authentication failed, due to
        invalid password.
    @type AUTH_FAILED_EVENT: L{str}
    """

    INVALID_USER_EVENT = "//event/client/basicauth/invaliduser"
    AUTH_FAILED_EVENT = "//event/client/basicauth/authfailed"

    def __init__(self, xs):
        self.xmlstream = xs

    def initialize(self):
        # Send request for auth fields
        iq = xmlstream.IQ(self.xmlstream, "get")
        iq.addElement(("jabber:iq:auth", "query"))
        jid = self.xmlstream.authenticator.jid
        iq.query.addElement("username", content=jid.user)

        d = iq.send()
        d.addCallbacks(self._cbAuthQuery, self._ebAuthQuery)
        return d

    def _cbAuthQuery(self, iq):
        jid = self.xmlstream.authenticator.jid
        password = self.xmlstream.authenticator.password

        # Construct auth request
        reply = xmlstream.IQ(self.xmlstream, "set")
        reply.addElement(("jabber:iq:auth", "query"))
        reply.query.addElement("username", content=jid.user)
        reply.query.addElement("resource", content=jid.resource)

        # Prefer digest over plaintext
        if DigestAuthQry.matches(iq):
            digest = xmlstream.hashPassword(self.xmlstream.sid, password)
            reply.query.addElement("digest", content=str(digest))
        else:
            reply.query.addElement("password", content=password)

        d = reply.send()
        d.addCallbacks(self._cbAuth, self._ebAuth)
        return d

    def _ebAuthQuery(self, failure):
        failure.trap(error.StanzaError)
        e = failure.value
        if e.condition == "not-authorized":
            self.xmlstream.dispatch(e.stanza, self.INVALID_USER_EVENT)
        else:
            self.xmlstream.dispatch(e.stanza, self.AUTH_FAILED_EVENT)

        return failure

    def _cbAuth(self, iq):
        pass

    def _ebAuth(self, failure):
        failure.trap(error.StanzaError)
        self.xmlstream.dispatch(failure.value.stanza, self.AUTH_FAILED_EVENT)
        return failure


class BasicAuthenticator(xmlstream.ConnectAuthenticator):
    """
    Authenticates an XmlStream against a Jabber server as a Client.

    This only implements non-SASL authentication, per
    U{JEP-0078<http://www.jabber.org/jeps/jep-0078.html>}. Additionally, this
    authenticator provides the ability to perform inline registration, per
    U{JEP-0077<http://www.jabber.org/jeps/jep-0077.html>}.

    Under normal circumstances, the BasicAuthenticator generates the
    L{xmlstream.STREAM_AUTHD_EVENT} once the stream has authenticated. However,
    it can also generate other events, such as:
      - L{INVALID_USER_EVENT} : Authentication failed, due to invalid username
      - L{AUTH_FAILED_EVENT} : Authentication failed, due to invalid password
      - L{REGISTER_FAILED_EVENT} : Registration failed

    If authentication fails for any reason, you can attempt to register by
    calling the L{registerAccount} method. If the registration succeeds, a
    L{xmlstream.STREAM_AUTHD_EVENT} will be fired. Otherwise, one of the above
    errors will be generated (again).


    @cvar INVALID_USER_EVENT: See L{IQAuthInitializer.INVALID_USER_EVENT}.
    @type INVALID_USER_EVENT: L{str}

    @cvar AUTH_FAILED_EVENT: See L{IQAuthInitializer.AUTH_FAILED_EVENT}.
    @type AUTH_FAILED_EVENT: L{str}

    @cvar REGISTER_FAILED_EVENT: Token to signal that registration failed.
    @type REGISTER_FAILED_EVENT: L{str}

    """

    namespace = "jabber:client"

    INVALID_USER_EVENT = IQAuthInitializer.INVALID_USER_EVENT
    AUTH_FAILED_EVENT = IQAuthInitializer.AUTH_FAILED_EVENT
    REGISTER_FAILED_EVENT = "//event/client/basicauth/registerfailed"

    def __init__(self, jid, password):
        xmlstream.ConnectAuthenticator.__init__(self, jid.host)
        self.jid = jid
        self.password = password

    def associateWithStream(self, xs):
        xs.version = (0, 0)
        xmlstream.ConnectAuthenticator.associateWithStream(self, xs)

        xs.initializers = [
            xmlstream.TLSInitiatingInitializer(xs, required=False),
            IQAuthInitializer(xs),
        ]

    # TODO: move registration into an Initializer?

    def registerAccount(self, username=None, password=None):
        if username:
            self.jid.user = username
        if password:
            self.password = password

        iq = IQ(self.xmlstream, "set")
        iq.addElement(("jabber:iq:register", "query"))
        iq.query.addElement("username", content=self.jid.user)
        iq.query.addElement("password", content=self.password)

        iq.addCallback(self._registerResultEvent)

        iq.send()

    def _registerResultEvent(self, iq):
        if iq["type"] == "result":
            # Registration succeeded -- go ahead and auth
            self.streamStarted()
        else:
            # Registration failed
            self.xmlstream.dispatch(iq, self.REGISTER_FAILED_EVENT)


class CheckVersionInitializer:
    """
    Initializer that checks if the minimum common stream version number is 1.0.
    """

    def __init__(self, xs):
        self.xmlstream = xs

    def initialize(self):
        if self.xmlstream.version < (1, 0):
            raise error.StreamError("unsupported-version")


class BindInitializer(xmlstream.BaseFeatureInitiatingInitializer):
    """
    Initializer that implements Resource Binding for the initiating entity.

    This protocol is documented in U{RFC 3920, section
    7<http://www.xmpp.org/specs/rfc3920.html#bind>}.
    """

    feature = (NS_XMPP_BIND, "bind")

    def start(self):
        iq = xmlstream.IQ(self.xmlstream, "set")
        bind = iq.addElement((NS_XMPP_BIND, "bind"))
        resource = self.xmlstream.authenticator.jid.resource
        if resource:
            bind.addElement("resource", content=resource)
        d = iq.send()
        d.addCallback(self.onBind)
        return d

    def onBind(self, iq):
        if iq.bind:
            self.xmlstream.authenticator.jid = JID(str(iq.bind.jid))


class SessionInitializer(xmlstream.BaseFeatureInitiatingInitializer):
    """
    Initializer that implements session establishment for the initiating
    entity.

    This protocol is defined in U{RFC 3921, section
    3<http://www.xmpp.org/specs/rfc3921.html#session>}.
    """

    feature = (NS_XMPP_SESSION, "session")

    def start(self):
        iq = xmlstream.IQ(self.xmlstream, "set")
        iq.addElement((NS_XMPP_SESSION, "session"))
        return iq.send()


def XMPPClientFactory(jid, password, configurationForTLS=None):
    """
    Client factory for XMPP 1.0 (only).

    This returns a L{xmlstream.XmlStreamFactory} with an L{XMPPAuthenticator}
    object to perform the stream initialization steps (such as authentication).

    @see: The notes at L{XMPPAuthenticator} describe how the C{jid} and
    C{password} parameters are to be used.

    @param jid: Jabber ID to connect with.
    @type jid: L{jid.JID}

    @param password: password to authenticate with.
    @type password: L{unicode}

    @param configurationForTLS: An object which creates appropriately
        configured TLS connections. This is passed to C{startTLS} on the
        transport and is preferably created using
        L{twisted.internet.ssl.optionsForClientTLS}. If L{None}, the default is
        to verify the server certificate against the trust roots as provided by
        the platform. See L{twisted.internet._sslverify.platformTrust}.
    @type configurationForTLS: L{IOpenSSLClientConnectionCreator} or L{None}

    @return: XML stream factory.
    @rtype: L{xmlstream.XmlStreamFactory}
    """
    a = XMPPAuthenticator(jid, password, configurationForTLS=configurationForTLS)
    return xmlstream.XmlStreamFactory(a)


class XMPPAuthenticator(xmlstream.ConnectAuthenticator):
    """
    Initializes an XmlStream connecting to an XMPP server as a Client.

    This authenticator performs the initialization steps needed to start
    exchanging XML stanzas with an XMPP server as an XMPP client. It checks if
    the server advertises XML stream version 1.0, negotiates TLS (when
    available), performs SASL authentication, binds a resource and establishes
    a session.

    Upon successful stream initialization, the L{xmlstream.STREAM_AUTHD_EVENT}
    event will be dispatched through the XML stream object. Otherwise, the
    L{xmlstream.INIT_FAILED_EVENT} event will be dispatched with a failure
    object.

    After inspection of the failure, initialization can then be restarted by
    calling L{ConnectAuthenticator.initializeStream}. For example, in case of
    authentication failure, a user may be given the opportunity to input the
    correct password.  By setting the L{password} instance variable and restarting
    initialization, the stream authentication step is then retried, and subsequent
    steps are performed if successful.

    @ivar jid: Jabber ID to authenticate with. This may contain a resource
               part, as a suggestion to the server for resource binding. A
               server may override this, though. If the resource part is left
               off, the server will generate a unique resource identifier.
               The server will always return the full Jabber ID in the
               resource binding step, and this is stored in this instance
               variable.
    @type jid: L{jid.JID}

    @ivar password: password to be used during SASL authentication.
    @type password: L{unicode}
    """

    namespace = "jabber:client"

    def __init__(self, jid, password, configurationForTLS=None):
        """
        @param configurationForTLS: An object which creates appropriately
            configured TLS connections. This is passed to C{startTLS} on the
            transport and is preferably created using
            L{twisted.internet.ssl.optionsForClientTLS}. If C{None}, the
            default is to verify the server certificate against the trust roots
            as provided by the platform. See
            L{twisted.internet._sslverify.platformTrust}.
        @type configurationForTLS: L{IOpenSSLClientConnectionCreator} or
            C{None}
        """
        xmlstream.ConnectAuthenticator.__init__(self, jid.host)
        self.jid = jid
        self.password = password
        self._configurationForTLS = configurationForTLS

    def associateWithStream(self, xs):
        """
        Register with the XML stream.

        Populates stream's list of initializers, along with their
        requiredness. This list is used by
        L{ConnectAuthenticator.initializeStream} to perform the initialization
        steps.
        """
        xmlstream.ConnectAuthenticator.associateWithStream(self, xs)

        xs.initializers = [
            CheckVersionInitializer(xs),
            xmlstream.TLSInitiatingInitializer(
                xs, required=True, configurationForTLS=self._configurationForTLS
            ),
            sasl.SASLInitiatingInitializer(xs, required=True),
            BindInitializer(xs, required=True),
            SessionInitializer(xs, required=False),
        ]

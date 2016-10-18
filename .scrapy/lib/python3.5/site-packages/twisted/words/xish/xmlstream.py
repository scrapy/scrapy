# -*- test-case-name: twisted.words.test.test_xmlstream -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
XML Stream processing.

An XML Stream is defined as a connection over which two XML documents are
exchanged during the lifetime of the connection, one for each direction. The
unit of interaction is a direct child element of the root element (stanza).

The most prominent use of XML Streams is Jabber, but this module is generically
usable. See Twisted Words for Jabber specific protocol support.

Maintainer: Ralph Meijer

@var STREAM_CONNECTED_EVENT: This event signals that the connection has been
    established.
@type STREAM_CONNECTED_EVENT: L{str}.

@var STREAM_END_EVENT: This event signals that the connection has been closed.
@type STREAM_END_EVENT: L{str}.

@var STREAM_ERROR_EVENT: This event signals that a parse error occurred.
@type STREAM_ERROR_EVENT: L{str}.

@var STREAM_START_EVENT: This event signals that the root element of the XML
    Stream has been received.
    For XMPP, this would be the C{<stream:stream ...>} opening tag.
@type STREAM_START_EVENT: L{str}.
"""

from __future__ import absolute_import, division

from twisted.python import failure
from twisted.python.compat import intern, unicode
from twisted.internet import protocol
from twisted.words.xish import domish, utility

STREAM_CONNECTED_EVENT = intern("//event/stream/connected")
STREAM_START_EVENT = intern("//event/stream/start")
STREAM_END_EVENT = intern("//event/stream/end")
STREAM_ERROR_EVENT = intern("//event/stream/error")

class XmlStream(protocol.Protocol, utility.EventDispatcher):
    """ Generic Streaming XML protocol handler.

    This protocol handler will parse incoming data as XML and dispatch events
    accordingly. Incoming stanzas can be handled by registering observers using
    XPath-like expressions that are matched against each stanza. See
    L{utility.EventDispatcher} for details.
    """
    def __init__(self):
        utility.EventDispatcher.__init__(self)
        self.stream = None
        self.rawDataOutFn = None
        self.rawDataInFn = None

    def _initializeStream(self):
        """ Sets up XML Parser. """
        self.stream = domish.elementStream()
        self.stream.DocumentStartEvent = self.onDocumentStart
        self.stream.ElementEvent = self.onElement
        self.stream.DocumentEndEvent = self.onDocumentEnd

    ### --------------------------------------------------------------
    ###
    ### Protocol events
    ###
    ### --------------------------------------------------------------

    def connectionMade(self):
        """ Called when a connection is made.

        Sets up the XML parser and dispatches the L{STREAM_CONNECTED_EVENT}
        event indicating the connection has been established.
        """
        self._initializeStream()
        self.dispatch(self, STREAM_CONNECTED_EVENT)

    def dataReceived(self, data):
        """ Called whenever data is received.

        Passes the data to the XML parser. This can result in calls to the
        DOM handlers. If a parse error occurs, the L{STREAM_ERROR_EVENT} event
        is called to allow for cleanup actions, followed by dropping the
        connection.
        """
        try:
            if self.rawDataInFn:
                self.rawDataInFn(data)
            self.stream.parse(data)
        except domish.ParserError:
            self.dispatch(failure.Failure(), STREAM_ERROR_EVENT)
            self.transport.loseConnection()

    def connectionLost(self, reason):
        """ Called when the connection is shut down.

        Dispatches the L{STREAM_END_EVENT}.
        """
        self.dispatch(reason, STREAM_END_EVENT)
        self.stream = None

    ### --------------------------------------------------------------
    ###
    ### DOM events
    ###
    ### --------------------------------------------------------------

    def onDocumentStart(self, rootElement):
        """ Called whenever the start tag of a root element has been received.

        Dispatches the L{STREAM_START_EVENT}.
        """
        self.dispatch(self, STREAM_START_EVENT)

    def onElement(self, element):
        """ Called whenever a direct child element of the root element has
        been received.

        Dispatches the received element.
        """
        self.dispatch(element)

    def onDocumentEnd(self):
        """ Called whenever the end tag of the root element has been received.

        Closes the connection. This causes C{connectionLost} being called.
        """
        self.transport.loseConnection()

    def setDispatchFn(self, fn):
        """ Set another function to handle elements. """
        self.stream.ElementEvent = fn

    def resetDispatchFn(self):
        """ Set the default function (C{onElement}) to handle elements. """
        self.stream.ElementEvent = self.onElement

    def send(self, obj):
        """ Send data over the stream.

        Sends the given C{obj} over the connection. C{obj} may be instances of
        L{domish.Element}, C{unicode} and C{str}. The first two will be
        properly serialized and/or encoded. C{str} objects must be in UTF-8
        encoding.

        Note: because it is easy to make mistakes in maintaining a properly
        encoded C{str} object, it is advised to use C{unicode} objects
        everywhere when dealing with XML Streams.

        @param obj: Object to be sent over the stream.
        @type obj: L{domish.Element}, L{domish} or C{str}

        """
        if domish.IElement.providedBy(obj):
            obj = obj.toXml()

        if isinstance(obj, unicode):
            obj = obj.encode('utf-8')

        if self.rawDataOutFn:
            self.rawDataOutFn(obj)

        self.transport.write(obj)



class BootstrapMixin(object):
    """
    XmlStream factory mixin to install bootstrap event observers.

    This mixin is for factories providing
    L{IProtocolFactory<twisted.internet.interfaces.IProtocolFactory>} to make
    sure bootstrap event observers are set up on protocols, before incoming
    data is processed. Such protocols typically derive from
    L{utility.EventDispatcher}, like L{XmlStream}.

    You can set up bootstrap event observers using C{addBootstrap}. The
    C{event} and C{fn} parameters correspond with the C{event} and
    C{observerfn} arguments to L{utility.EventDispatcher.addObserver}.

    @since: 8.2.
    @ivar bootstraps: The list of registered bootstrap event observers.
    @type bootstrap: C{list}
    """

    def __init__(self):
        self.bootstraps = []


    def installBootstraps(self, dispatcher):
        """
        Install registered bootstrap observers.

        @param dispatcher: Event dispatcher to add the observers to.
        @type dispatcher: L{utility.EventDispatcher}
        """
        for event, fn in self.bootstraps:
            dispatcher.addObserver(event, fn)


    def addBootstrap(self, event, fn):
        """
        Add a bootstrap event handler.

        @param event: The event to register an observer for.
        @type event: C{str} or L{xpath.XPathQuery}
        @param fn: The observer callable to be registered.
        """
        self.bootstraps.append((event, fn))


    def removeBootstrap(self, event, fn):
        """
        Remove a bootstrap event handler.

        @param event: The event the observer is registered for.
        @type event: C{str} or L{xpath.XPathQuery}
        @param fn: The registered observer callable.
        """
        self.bootstraps.remove((event, fn))



class XmlStreamFactoryMixin(BootstrapMixin):
    """
    XmlStream factory mixin that takes care of event handlers.

    All positional and keyword arguments passed to create this factory are
    passed on as-is to the protocol.

    @ivar args: Positional arguments passed to the protocol upon instantiation.
    @type args: C{tuple}.
    @ivar kwargs: Keyword arguments passed to the protocol upon instantiation.
    @type kwargs: C{dict}.
    """

    def __init__(self, *args, **kwargs):
        BootstrapMixin.__init__(self)
        self.args = args
        self.kwargs = kwargs


    def buildProtocol(self, addr):
        """
        Create an instance of XmlStream.

        The returned instance will have bootstrap event observers registered
        and will proceed to handle input on an incoming connection.
        """
        xs = self.protocol(*self.args, **self.kwargs)
        xs.factory = self
        self.installBootstraps(xs)
        return xs



class XmlStreamFactory(XmlStreamFactoryMixin,
                       protocol.ReconnectingClientFactory):
    """
    Factory for XmlStream protocol objects as a reconnection client.
    """

    protocol = XmlStream

    def buildProtocol(self, addr):
        """
        Create a protocol instance.

        Overrides L{XmlStreamFactoryMixin.buildProtocol} to work with
        a L{ReconnectingClientFactory}. As this is called upon having an
        connection established, we are resetting the delay for reconnection
        attempts when the connection is lost again.
        """
        self.resetDelay()
        return XmlStreamFactoryMixin.buildProtocol(self, addr)

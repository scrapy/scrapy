# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Public Jabber Interfaces.
"""

from zope.interface import Attribute, Interface

class IInitializer(Interface):
    """
    Interface for XML stream initializers.

    Initializers perform a step in getting the XML stream ready to be
    used for the exchange of XML stanzas.
    """



class IInitiatingInitializer(IInitializer):
    """
    Interface for XML stream initializers for the initiating entity.
    """

    xmlstream = Attribute("""The associated XML stream""")

    def initialize():
        """
        Initiate the initialization step.

        May return a deferred when the initialization is done asynchronously.
        """



class IIQResponseTracker(Interface):
    """
    IQ response tracker interface.

    The XMPP stanza C{iq} has a request-response nature that fits
    naturally with deferreds. You send out a request and when the response
    comes back a deferred is fired.

    The L{twisted.words.protocols.jabber.client.IQ} class implements a C{send}
    method that returns a deferred. This deferred is put in a dictionary that
    is kept in an L{XmlStream} object, keyed by the request stanzas C{id}
    attribute.

    An object providing this interface (usually an instance of L{XmlStream}),
    keeps the said dictionary and sets observers on the iq stanzas of type
    C{result} and C{error} and lets the callback fire the associated deferred.
    """
    iqDeferreds = Attribute("Dictionary of deferreds waiting for an iq "
                             "response")



class IXMPPHandler(Interface):
    """
    Interface for XMPP protocol handlers.

    Objects that provide this interface can be added to a stream manager to
    handle of (part of) an XMPP extension protocol.
    """

    parent = Attribute("""XML stream manager for this handler""")
    xmlstream = Attribute("""The managed XML stream""")

    def setHandlerParent(parent):
        """
        Set the parent of the handler.

        @type parent: L{IXMPPHandlerCollection}
        """


    def disownHandlerParent(parent):
        """
        Remove the parent of the handler.

        @type parent: L{IXMPPHandlerCollection}
        """


    def makeConnection(xs):
        """
        A connection over the underlying transport of the XML stream has been
        established.

        At this point, no traffic has been exchanged over the XML stream
        given in C{xs}.

        This should setup L{xmlstream} and call L{connectionMade}.

        @type xs:
               L{twisted.words.protocols.jabber.xmlstream.XmlStream}
        """


    def connectionMade():
        """
        Called after a connection has been established.

        This method can be used to change properties of the XML Stream, its
        authenticator or the stream manager prior to stream initialization
        (including authentication).
        """


    def connectionInitialized():
        """
        The XML stream has been initialized.

        At this point, authentication was successful, and XML stanzas can be
        exchanged over the XML stream L{xmlstream}. This method can be
        used to setup observers for incoming stanzas.
        """


    def connectionLost(reason):
        """
        The XML stream has been closed.

        Subsequent use of C{parent.send} will result in data being queued
        until a new connection has been established.

        @type reason: L{twisted.python.failure.Failure}
        """



class IXMPPHandlerCollection(Interface):
    """
    Collection of handlers.

    Contain several handlers and manage their connection.
    """

    def __iter__():
        """
        Get an iterator over all child handlers.
        """


    def addHandler(handler):
        """
        Add a child handler.

        @type handler: L{IXMPPHandler}
        """


    def removeHandler(handler):
        """
        Remove a child handler.

        @type handler: L{IXMPPHandler}
        """



class IService(Interface):
    """
    External server-side component service interface.

    Services that provide this interface can be added to L{ServiceManager} to
    implement (part of) the functionality of the server-side component.
    """

    def componentConnected(xs):
        """
        Parent component has established a connection.

        At this point, authentication was successful, and XML stanzas
        can be exchanged over the XML stream C{xs}. This method can be used
        to setup observers for incoming stanzas.

        @param xs: XML Stream that represents the established connection.
        @type xs: L{xmlstream.XmlStream}
        """


    def componentDisconnected():
        """
        Parent component has lost the connection to the Jabber server.

        Subsequent use of C{self.parent.send} will result in data being
        queued until a new connection has been established.
        """


    def transportConnected(xs):
        """
        Parent component has established a connection over the underlying
        transport.

        At this point, no traffic has been exchanged over the XML stream. This
        method can be used to change properties of the XML Stream (in C{xs}),
        the service manager or it's authenticator prior to stream
        initialization (including authentication).
        """

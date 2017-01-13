# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.words.xish.xmlstream}.
"""

from __future__ import absolute_import, division

from twisted.internet import protocol
from twisted.python import failure
from twisted.trial import unittest
from twisted.words.xish import domish, utility, xmlstream

class XmlStreamTests(unittest.TestCase):
    def setUp(self):
        self.connectionLostMsg = "no reason"
        self.outlist = []
        self.xmlstream = xmlstream.XmlStream()
        self.xmlstream.transport = self
        self.xmlstream.transport.write = self.outlist.append


    def loseConnection(self):
        """
        Stub loseConnection because we are a transport.
        """
        self.xmlstream.connectionLost(failure.Failure(
            Exception(self.connectionLostMsg)))


    def test_send(self):
        """
        Calling L{xmlstream.XmlStream.send} results in the data being written
        to the transport.
        """
        self.xmlstream.connectionMade()
        self.xmlstream.send(b"<root>")
        self.assertEqual(self.outlist[0], b"<root>")


    def test_receiveRoot(self):
        """
        Receiving the starttag of the root element results in stream start.
        """
        streamStarted = []

        def streamStartEvent(rootelem):
            streamStarted.append(None)

        self.xmlstream.addObserver(xmlstream.STREAM_START_EVENT,
                                   streamStartEvent)
        self.xmlstream.connectionMade()
        self.xmlstream.dataReceived("<root>")
        self.assertEqual(1, len(streamStarted))


    def test_receiveBadXML(self):
        """
        Receiving malformed XML results in an L{STREAM_ERROR_EVENT}.
        """
        streamError = []
        streamEnd = []

        def streamErrorEvent(reason):
            streamError.append(reason)

        def streamEndEvent(_):
            streamEnd.append(None)

        self.xmlstream.addObserver(xmlstream.STREAM_ERROR_EVENT,
                                   streamErrorEvent)
        self.xmlstream.addObserver(xmlstream.STREAM_END_EVENT,
                                   streamEndEvent)
        self.xmlstream.connectionMade()

        self.xmlstream.dataReceived("<root>")
        self.assertEqual(0, len(streamError))
        self.assertEqual(0, len(streamEnd))

        self.xmlstream.dataReceived("<child><unclosed></child>")
        self.assertEqual(1, len(streamError))
        self.assertTrue(streamError[0].check(domish.ParserError))
        self.assertEqual(1, len(streamEnd))


    def test_streamEnd(self):
        """
        Ending the stream fires a L{STREAM_END_EVENT}.
        """
        streamEnd = []

        def streamEndEvent(reason):
            streamEnd.append(reason)

        self.xmlstream.addObserver(xmlstream.STREAM_END_EVENT,
                                   streamEndEvent)
        self.xmlstream.connectionMade()
        self.loseConnection()
        self.assertEqual(1, len(streamEnd))
        self.assertIsInstance(streamEnd[0], failure.Failure)
        self.assertEqual(streamEnd[0].getErrorMessage(),
                self.connectionLostMsg)



class DummyProtocol(protocol.Protocol, utility.EventDispatcher):
    """
    I am a protocol with an event dispatcher without further processing.

    This protocol is only used for testing XmlStreamFactoryMixin to make
    sure the bootstrap observers are added to the protocol instance.
    """

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.observers = []

        utility.EventDispatcher.__init__(self)



class BootstrapMixinTests(unittest.TestCase):
    """
    Tests for L{xmlstream.BootstrapMixin}.

    @ivar factory: Instance of the factory or mixin under test.
    """

    def setUp(self):
        self.factory = xmlstream.BootstrapMixin()


    def test_installBootstraps(self):
        """
        Dispatching an event fires registered bootstrap observers.
        """
        called = []

        def cb(data):
            called.append(data)

        dispatcher = DummyProtocol()
        self.factory.addBootstrap('//event/myevent', cb)
        self.factory.installBootstraps(dispatcher)

        dispatcher.dispatch(None, '//event/myevent')
        self.assertEqual(1, len(called))


    def test_addAndRemoveBootstrap(self):
        """
        Test addition and removal of a bootstrap event handler.
        """

        called = []

        def cb(data):
            called.append(data)

        self.factory.addBootstrap('//event/myevent', cb)
        self.factory.removeBootstrap('//event/myevent', cb)

        dispatcher = DummyProtocol()
        self.factory.installBootstraps(dispatcher)

        dispatcher.dispatch(None, '//event/myevent')
        self.assertFalse(called)



class GenericXmlStreamFactoryTestsMixin(BootstrapMixinTests):
    """
    Generic tests for L{XmlStream} factories.
    """

    def setUp(self):
        self.factory = xmlstream.XmlStreamFactory()


    def test_buildProtocolInstallsBootstraps(self):
        """
        The protocol factory installs bootstrap event handlers on the protocol.
        """
        called = []

        def cb(data):
            called.append(data)

        self.factory.addBootstrap('//event/myevent', cb)

        xs = self.factory.buildProtocol(None)
        xs.dispatch(None, '//event/myevent')

        self.assertEqual(1, len(called))


    def test_buildProtocolStoresFactory(self):
        """
        The protocol factory is saved in the protocol.
        """
        xs = self.factory.buildProtocol(None)
        self.assertIdentical(self.factory, xs.factory)



class XmlStreamFactoryMixinTests(GenericXmlStreamFactoryTestsMixin):
    """
    Tests for L{xmlstream.XmlStreamFactoryMixin}.
    """

    def setUp(self):
        self.factory = xmlstream.XmlStreamFactoryMixin(None, test=None)
        self.factory.protocol = DummyProtocol


    def test_buildProtocolFactoryArguments(self):
        """
        Arguments passed to the factory are passed to protocol on
        instantiation.
        """
        xs = self.factory.buildProtocol(None)

        self.assertEqual((None,), xs.args)
        self.assertEqual({'test': None}, xs.kwargs)

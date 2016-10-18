# Copyright (c) 2005 Divmod, Inc.
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.protocols.amp}.
"""

from __future__ import absolute_import, division

import datetime
import decimal

from zope.interface import implementer
from zope.interface.verify import verifyClass, verifyObject

from twisted.python import filepath
from twisted.python.compat import intToBytes
from twisted.python.failure import Failure
from twisted.protocols import amp
from twisted.trial import unittest
from twisted.internet import (
    address, protocol, defer, error, reactor, interfaces)
from twisted.test import iosim
from twisted.test.proto_helpers import StringTransport

ssl = None
try:
    from twisted.internet import ssl
except ImportError:
    pass

if ssl and not ssl.supported:
    ssl = None

if ssl is None:
    skipSSL = "SSL not available"
else:
    skipSSL = None



tz = amp._FixedOffsetTZInfo.fromSignHoursMinutes



class TestProto(protocol.Protocol):
    """
    A trivial protocol for use in testing where a L{Protocol} is expected.

    @ivar instanceId: the id of this instance
    @ivar onConnLost: deferred that will fired when the connection is lost
    @ivar dataToSend: data to send on the protocol
    """

    instanceCount = 0

    def __init__(self, onConnLost, dataToSend):
        assert isinstance(dataToSend, bytes), repr(dataToSend)
        self.onConnLost = onConnLost
        self.dataToSend = dataToSend
        self.instanceId = TestProto.instanceCount
        TestProto.instanceCount = TestProto.instanceCount + 1


    def connectionMade(self):
        self.data = []
        self.transport.write(self.dataToSend)


    def dataReceived(self, bytes):
        self.data.append(bytes)


    def connectionLost(self, reason):
        self.onConnLost.callback(self.data)


    def __repr__(self):
        """
        Custom repr for testing to avoid coupling amp tests with repr from
        L{Protocol}

        Returns a string which contains a unique identifier that can be looked
        up using the instanceId property::

            <TestProto #3>
        """
        return "<TestProto #%d>" % (self.instanceId,)



class SimpleSymmetricProtocol(amp.AMP):

    def sendHello(self, text):
        return self.callRemoteString(
            b"hello",
            hello=text)

    def amp_HELLO(self, box):
        return amp.Box(hello=box[b'hello'])



class UnfriendlyGreeting(Exception):
    """Greeting was insufficiently kind.
    """

class DeathThreat(Exception):
    """Greeting was insufficiently kind.
    """

class UnknownProtocol(Exception):
    """Asked to switch to the wrong protocol.
    """


class TransportPeer(amp.Argument):
    # this serves as some informal documentation for how to get variables from
    # the protocol or your environment and pass them to methods as arguments.
    def retrieve(self, d, name, proto):
        return b''

    def fromStringProto(self, notAString, proto):
        return proto.transport.getPeer()

    def toBox(self, name, strings, objects, proto):
        return



class Hello(amp.Command):

    commandName = b'hello'

    arguments = [(b'hello', amp.String()),
                 (b'optional', amp.Boolean(optional=True)),
                 (b'print', amp.Unicode(optional=True)),
                 (b'from', TransportPeer(optional=True)),
                 (b'mixedCase', amp.String(optional=True)),
                 (b'dash-arg', amp.String(optional=True)),
                 (b'underscore_arg', amp.String(optional=True))]

    response = [(b'hello', amp.String()),
                (b'print', amp.Unicode(optional=True))]

    errors = {UnfriendlyGreeting: b'UNFRIENDLY'}

    fatalErrors = {DeathThreat: b'DEAD'}

class NoAnswerHello(Hello):
    commandName = Hello.commandName
    requiresAnswer = False

class FutureHello(amp.Command):
    commandName = b'hello'

    arguments = [(b'hello', amp.String()),
                 (b'optional', amp.Boolean(optional=True)),
                 (b'print', amp.Unicode(optional=True)),
                 (b'from', TransportPeer(optional=True)),
                 (b'bonus', amp.String(optional=True)), # addt'l arguments
                                                        # should generally be
                                                        # added at the end, and
                                                        # be optional...
                 ]

    response = [(b'hello', amp.String()),
                (b'print', amp.Unicode(optional=True))]

    errors = {UnfriendlyGreeting: b'UNFRIENDLY'}

class WTF(amp.Command):
    """
    An example of an invalid command.
    """


class BrokenReturn(amp.Command):
    """ An example of a perfectly good command, but the handler is going to return
    None...
    """

    commandName = b'broken_return'

class Goodbye(amp.Command):
    # commandName left blank on purpose: this tests implicit command names.
    response = [(b'goodbye', amp.String())]
    responseType = amp.QuitBox

class WaitForever(amp.Command):
    commandName = b'wait_forever'

class GetList(amp.Command):
    commandName = b'getlist'
    arguments = [(b'length', amp.Integer())]
    response = [(b'body', amp.AmpList([(b'x', amp.Integer())]))]

class DontRejectMe(amp.Command):
    commandName = b'dontrejectme'
    arguments = [
            (b'magicWord', amp.Unicode()),
            (b'list', amp.AmpList([(b'name', amp.Unicode())], optional=True)),
            ]
    response = [(b'response', amp.Unicode())]

class SecuredPing(amp.Command):
    # XXX TODO: actually make this refuse to send over an insecure connection
    response = [(b'pinged', amp.Boolean())]

class TestSwitchProto(amp.ProtocolSwitchCommand):
    commandName = b'Switch-Proto'

    arguments = [
        (b'name', amp.String()),
        ]
    errors = {UnknownProtocol: b'UNKNOWN'}

class SingleUseFactory(protocol.ClientFactory):
    def __init__(self, proto):
        self.proto = proto
        self.proto.factory = self

    def buildProtocol(self, addr):
        p, self.proto = self.proto, None
        return p

    reasonFailed = None

    def clientConnectionFailed(self, connector, reason):
        self.reasonFailed = reason
        return

THING_I_DONT_UNDERSTAND = b'gwebol nargo'
class ThingIDontUnderstandError(Exception):
    pass

class FactoryNotifier(amp.AMP):
    factory = None
    def connectionMade(self):
        if self.factory is not None:
            self.factory.theProto = self
            if hasattr(self.factory, 'onMade'):
                self.factory.onMade.callback(None)

    def emitpong(self):
        from twisted.internet.interfaces import ISSLTransport
        if not ISSLTransport.providedBy(self.transport):
            raise DeathThreat("only send secure pings over secure channels")
        return {'pinged': True}
    SecuredPing.responder(emitpong)


class SimpleSymmetricCommandProtocol(FactoryNotifier):
    maybeLater = None
    def __init__(self, onConnLost=None):
        amp.AMP.__init__(self)
        self.onConnLost = onConnLost

    def sendHello(self, text):
        return self.callRemote(Hello, hello=text)

    def sendUnicodeHello(self, text, translation):
        return self.callRemote(Hello, hello=text, Print=translation)

    greeted = False

    def cmdHello(self, hello, From, optional=None, Print=None,
                 mixedCase=None, dash_arg=None, underscore_arg=None):
        assert From == self.transport.getPeer()
        if hello == THING_I_DONT_UNDERSTAND:
            raise ThingIDontUnderstandError()
        if hello.startswith(b'fuck'):
            raise UnfriendlyGreeting("Don't be a dick.")
        if hello == b'die':
            raise DeathThreat("aieeeeeeeee")
        result = dict(hello=hello)
        if Print is not None:
            result.update(dict(Print=Print))
        self.greeted = True
        return result
    Hello.responder(cmdHello)

    def cmdGetlist(self, length):
        return {'body': [dict(x=1)] * length}
    GetList.responder(cmdGetlist)

    def okiwont(self, magicWord, list=None):
        if list is None:
            response = u'list omitted'
        else:
            response = u'%s accepted' % (list[0]['name'])
        return dict(response=response)
    DontRejectMe.responder(okiwont)

    def waitforit(self):
        self.waiting = defer.Deferred()
        return self.waiting
    WaitForever.responder(waitforit)

    def saybye(self):
        return dict(goodbye=b"everyone")
    Goodbye.responder(saybye)

    def switchToTestProtocol(self, fail=False):
        if fail:
            name = b'no-proto'
        else:
            name = b'test-proto'
        p = TestProto(self.onConnLost, SWITCH_CLIENT_DATA)
        return self.callRemote(
            TestSwitchProto,
            SingleUseFactory(p), name=name).addCallback(lambda ign: p)

    def switchit(self, name):
        if name == b'test-proto':
            return TestProto(self.onConnLost, SWITCH_SERVER_DATA)
        raise UnknownProtocol(name)
    TestSwitchProto.responder(switchit)

    def donothing(self):
        return None
    BrokenReturn.responder(donothing)


class DeferredSymmetricCommandProtocol(SimpleSymmetricCommandProtocol):
    def switchit(self, name):
        if name == b'test-proto':
            self.maybeLaterProto = TestProto(self.onConnLost, SWITCH_SERVER_DATA)
            self.maybeLater = defer.Deferred()
            return self.maybeLater
    TestSwitchProto.responder(switchit)

class BadNoAnswerCommandProtocol(SimpleSymmetricCommandProtocol):
    def badResponder(self, hello, From, optional=None, Print=None,
                     mixedCase=None, dash_arg=None, underscore_arg=None):
        """
        This responder does nothing and forgets to return a dictionary.
        """
    NoAnswerHello.responder(badResponder)

class NoAnswerCommandProtocol(SimpleSymmetricCommandProtocol):
    def goodNoAnswerResponder(self, hello, From, optional=None, Print=None,
                              mixedCase=None, dash_arg=None, underscore_arg=None):
        return dict(hello=hello+b"-noanswer")
    NoAnswerHello.responder(goodNoAnswerResponder)

def connectedServerAndClient(ServerClass=SimpleSymmetricProtocol,
                             ClientClass=SimpleSymmetricProtocol,
                             *a, **kw):
    """Returns a 3-tuple: (client, server, pump)
    """
    return iosim.connectedServerAndClient(
        ServerClass, ClientClass,
        *a, **kw)

class TotallyDumbProtocol(protocol.Protocol):
    buf = b''
    def dataReceived(self, data):
        self.buf += data

class LiteralAmp(amp.AMP):
    def __init__(self):
        self.boxes = []

    def ampBoxReceived(self, box):
        self.boxes.append(box)
        return



class AmpBoxTests(unittest.TestCase):
    """
    Test a few essential properties of AMP boxes, mostly with respect to
    serialization correctness.
    """

    def test_serializeStr(self):
        """
        Make sure that strs serialize to strs.
        """
        a = amp.AmpBox(key=b'value')
        self.assertEqual(type(a.serialize()), bytes)

    def test_serializeUnicodeKeyRaises(self):
        """
        Verify that TypeError is raised when trying to serialize Unicode keys.
        """
        a = amp.AmpBox(**{u'key': 'value'})
        self.assertRaises(TypeError, a.serialize)

    def test_serializeUnicodeValueRaises(self):
        """
        Verify that TypeError is raised when trying to serialize Unicode
        values.
        """
        a = amp.AmpBox(key=u'value')
        self.assertRaises(TypeError, a.serialize)



class ParsingTests(unittest.TestCase):

    def test_booleanValues(self):
        """
        Verify that the Boolean parser parses 'True' and 'False', but nothing
        else.
        """
        b = amp.Boolean()
        self.assertTrue(b.fromString(b"True"))
        self.assertFalse(b.fromString(b"False"))
        self.assertRaises(TypeError, b.fromString, b"ninja")
        self.assertRaises(TypeError, b.fromString, b"true")
        self.assertRaises(TypeError, b.fromString, b"TRUE")
        self.assertEqual(b.toString(True), b'True')
        self.assertEqual(b.toString(False), b'False')

    def test_pathValueRoundTrip(self):
        """
        Verify the 'Path' argument can parse and emit a file path.
        """
        fp = filepath.FilePath(self.mktemp())
        p = amp.Path()
        s = p.toString(fp)
        v = p.fromString(s)
        self.assertIsNot(fp, v) # sanity check
        self.assertEqual(fp, v)


    def test_sillyEmptyThing(self):
        """
        Test that empty boxes raise an error; they aren't supposed to be sent
        on purpose.
        """
        a = amp.AMP()
        return self.assertRaises(amp.NoEmptyBoxes, a.ampBoxReceived, amp.Box())


    def test_ParsingRoundTrip(self):
        """
        Verify that various kinds of data make it through the encode/parse
        round-trip unharmed.
        """
        c, s, p = connectedServerAndClient(ClientClass=LiteralAmp,
                                           ServerClass=LiteralAmp)

        SIMPLE = (b'simple', b'test')
        CE = (b'ceq', b': ')
        CR = (b'crtest', b'test\r')
        LF = (b'lftest', b'hello\n')
        NEWLINE = (b'newline', b'test\r\none\r\ntwo')
        NEWLINE2 = (b'newline2', b'test\r\none\r\n two')
        BODYTEST = (b'body', b'blah\r\n\r\ntesttest')

        testData = [
            [SIMPLE],
            [SIMPLE, BODYTEST],
            [SIMPLE, CE],
            [SIMPLE, CR],
            [SIMPLE, CE, CR, LF],
            [CE, CR, LF],
            [SIMPLE, NEWLINE, CE, NEWLINE2],
            [BODYTEST, SIMPLE, NEWLINE]
            ]

        for test in testData:
            jb = amp.Box()
            jb.update(dict(test))
            jb._sendTo(c)
            p.flush()
            self.assertEqual(s.boxes[-1], jb)



class FakeLocator(object):
    """
    This is a fake implementation of the interface implied by
    L{CommandLocator}.
    """
    def __init__(self):
        """
        Remember the given keyword arguments as a set of responders.
        """
        self.commands = {}


    def locateResponder(self, commandName):
        """
        Look up and return a function passed as a keyword argument of the given
        name to the constructor.
        """
        return self.commands[commandName]


class FakeSender:
    """
    This is a fake implementation of the 'box sender' interface implied by
    L{AMP}.
    """
    def __init__(self):
        """
        Create a fake sender and initialize the list of received boxes and
        unhandled errors.
        """
        self.sentBoxes = []
        self.unhandledErrors = []
        self.expectedErrors = 0


    def expectError(self):
        """
        Expect one error, so that the test doesn't fail.
        """
        self.expectedErrors += 1


    def sendBox(self, box):
        """
        Accept a box, but don't do anything.
        """
        self.sentBoxes.append(box)


    def unhandledError(self, failure):
        """
        Deal with failures by instantly re-raising them for easier debugging.
        """
        self.expectedErrors -= 1
        if self.expectedErrors < 0:
            failure.raiseException()
        else:
            self.unhandledErrors.append(failure)



class CommandDispatchTests(unittest.TestCase):
    """
    The AMP CommandDispatcher class dispatches converts AMP boxes into commands
    and responses using Command.responder decorator.

    Note: Originally, AMP's factoring was such that many tests for this
    functionality are now implemented as full round-trip tests in L{AMPTests}.
    Future tests should be written at this level instead, to ensure API
    compatibility and to provide more granular, readable units of test
    coverage.
    """

    def setUp(self):
        """
        Create a dispatcher to use.
        """
        self.locator = FakeLocator()
        self.sender = FakeSender()
        self.dispatcher = amp.BoxDispatcher(self.locator)
        self.dispatcher.startReceivingBoxes(self.sender)


    def test_receivedAsk(self):
        """
        L{CommandDispatcher.ampBoxReceived} should locate the appropriate
        command in its responder lookup, based on the '_ask' key.
        """
        received = []
        def thunk(box):
            received.append(box)
            return amp.Box({"hello": "goodbye"})
        input = amp.Box(_command="hello",
                        _ask="test-command-id",
                        hello="world")
        self.locator.commands['hello'] = thunk
        self.dispatcher.ampBoxReceived(input)
        self.assertEqual(received, [input])


    def test_sendUnhandledError(self):
        """
        L{CommandDispatcher} should relay its unhandled errors in responding to
        boxes to its boxSender.
        """
        err = RuntimeError("something went wrong, oh no")
        self.sender.expectError()
        self.dispatcher.unhandledError(Failure(err))
        self.assertEqual(len(self.sender.unhandledErrors), 1)
        self.assertEqual(self.sender.unhandledErrors[0].value, err)


    def test_unhandledSerializationError(self):
        """
        Errors during serialization ought to be relayed to the sender's
        unhandledError method.
        """
        err = RuntimeError("something undefined went wrong")
        def thunk(result):
            class BrokenBox(amp.Box):
                def _sendTo(self, proto):
                    raise err
            return BrokenBox()
        self.locator.commands['hello'] = thunk
        input = amp.Box(_command="hello",
                        _ask="test-command-id",
                        hello="world")
        self.sender.expectError()
        self.dispatcher.ampBoxReceived(input)
        self.assertEqual(len(self.sender.unhandledErrors), 1)
        self.assertEqual(self.sender.unhandledErrors[0].value, err)


    def test_callRemote(self):
        """
        L{CommandDispatcher.callRemote} should emit a properly formatted '_ask'
        box to its boxSender and record an outstanding L{Deferred}.  When a
        corresponding '_answer' packet is received, the L{Deferred} should be
        fired, and the results translated via the given L{Command}'s response
        de-serialization.
        """
        D = self.dispatcher.callRemote(Hello, hello=b'world')
        self.assertEqual(self.sender.sentBoxes,
                          [amp.AmpBox(_command=b"hello",
                                      _ask=b"1",
                                      hello=b"world")])
        answers = []
        D.addCallback(answers.append)
        self.assertEqual(answers, [])
        self.dispatcher.ampBoxReceived(amp.AmpBox({b'hello': b"yay",
                                                   b'print': b"ignored",
                                                   b'_answer': b"1"}))
        self.assertEqual(answers, [dict(hello=b"yay",
                                         Print=u"ignored")])


    def _localCallbackErrorLoggingTest(self, callResult):
        """
        Verify that C{callResult} completes with a L{None} result and that an
        unhandled error has been logged.
        """
        finalResult = []
        callResult.addBoth(finalResult.append)

        self.assertEqual(1, len(self.sender.unhandledErrors))
        self.assertIsInstance(
            self.sender.unhandledErrors[0].value, ZeroDivisionError)

        self.assertEqual([None], finalResult)


    def test_callRemoteSuccessLocalCallbackErrorLogging(self):
        """
        If the last callback on the L{Deferred} returned by C{callRemote} (added
        by application code calling C{callRemote}) fails, the failure is passed
        to the sender's C{unhandledError} method.
        """
        self.sender.expectError()

        callResult = self.dispatcher.callRemote(Hello, hello=b'world')
        callResult.addCallback(lambda result: 1 // 0)

        self.dispatcher.ampBoxReceived(amp.AmpBox({
                    b'hello': b"yay", b'print': b"ignored", b'_answer': b"1"}))

        self._localCallbackErrorLoggingTest(callResult)


    def test_callRemoteErrorLocalCallbackErrorLogging(self):
        """
        Like L{test_callRemoteSuccessLocalCallbackErrorLogging}, but for the
        case where the L{Deferred} returned by C{callRemote} fails.
        """
        self.sender.expectError()

        callResult = self.dispatcher.callRemote(Hello, hello=b'world')
        callResult.addErrback(lambda result: 1 // 0)

        self.dispatcher.ampBoxReceived(amp.AmpBox({
                    b'_error': b'1', b'_error_code': b'bugs',
                    b'_error_description': b'stuff'}))

        self._localCallbackErrorLoggingTest(callResult)



class SimpleGreeting(amp.Command):
    """
    A very simple greeting command that uses a few basic argument types.
    """
    commandName = b'simple'
    arguments = [(b'greeting', amp.Unicode()),
                 (b'cookie', amp.Integer())]
    response = [(b'cookieplus', amp.Integer())]



class TestLocator(amp.CommandLocator):
    """
    A locator which implements a responder to the 'simple' command.
    """
    def __init__(self):
        self.greetings = []


    def greetingResponder(self, greeting, cookie):
        self.greetings.append((greeting, cookie))
        return dict(cookieplus=cookie + 3)
    greetingResponder = SimpleGreeting.responder(greetingResponder)



class OverridingLocator(TestLocator):
    """
    A locator which overrides the responder to the 'simple' command.
    """

    def greetingResponder(self, greeting, cookie):
        """
        Return a different cookieplus than L{TestLocator.greetingResponder}.
        """
        self.greetings.append((greeting, cookie))
        return dict(cookieplus=cookie + 4)
    greetingResponder = SimpleGreeting.responder(greetingResponder)



class InheritingLocator(OverridingLocator):
    """
    This locator should inherit the responder from L{OverridingLocator}.
    """



class OverrideLocatorAMP(amp.AMP):
    def __init__(self):
        amp.AMP.__init__(self)
        self.customResponder = object()
        self.expectations = {b"custom": self.customResponder}
        self.greetings = []


    def lookupFunction(self, name):
        """
        Override the deprecated lookupFunction function.
        """
        if name in self.expectations:
            result = self.expectations[name]
            return result
        else:
            return super(OverrideLocatorAMP, self).lookupFunction(name)


    def greetingResponder(self, greeting, cookie):
        self.greetings.append((greeting, cookie))
        return dict(cookieplus=cookie + 3)
    greetingResponder = SimpleGreeting.responder(greetingResponder)




class CommandLocatorTests(unittest.TestCase):
    """
    The CommandLocator should enable users to specify responders to commands as
    functions that take structured objects, annotated with metadata.
    """

    def _checkSimpleGreeting(self, locatorClass, expected):
        """
        Check that a locator of type C{locatorClass} finds a responder
        for command named I{simple} and that the found responder answers
        with the C{expected} result to a C{SimpleGreeting<"ni hao", 5>}
        command.
        """
        locator = locatorClass()
        responderCallable = locator.locateResponder(b"simple")
        result = responderCallable(amp.Box(greeting=b"ni hao", cookie=b"5"))
        def done(values):
            self.assertEqual(values, amp.AmpBox(cookieplus=intToBytes(expected)))
        return result.addCallback(done)


    def test_responderDecorator(self):
        """
        A method on a L{CommandLocator} subclass decorated with a L{Command}
        subclass's L{responder} decorator should be returned from
        locateResponder, wrapped in logic to serialize and deserialize its
        arguments.
        """
        return self._checkSimpleGreeting(TestLocator, 8)


    def test_responderOverriding(self):
        """
        L{CommandLocator} subclasses can override a responder inherited from
        a base class by using the L{Command.responder} decorator to register
        a new responder method.
        """
        return self._checkSimpleGreeting(OverridingLocator, 9)


    def test_responderInheritance(self):
        """
        Responder lookup follows the same rules as normal method lookup
        rules, particularly with respect to inheritance.
        """
        return self._checkSimpleGreeting(InheritingLocator, 9)


    def test_lookupFunctionDeprecatedOverride(self):
        """
        Subclasses which override locateResponder under its old name,
        lookupFunction, should have the override invoked instead.  (This tests
        an AMP subclass, because in the version of the code that could invoke
        this deprecated code path, there was no L{CommandLocator}.)
        """
        locator = OverrideLocatorAMP()
        customResponderObject = self.assertWarns(
            PendingDeprecationWarning,
            "Override locateResponder, not lookupFunction.",
            __file__, lambda : locator.locateResponder(b"custom"))
        self.assertEqual(locator.customResponder, customResponderObject)
        # Make sure upcalling works too
        normalResponderObject = self.assertWarns(
            PendingDeprecationWarning,
            "Override locateResponder, not lookupFunction.",
            __file__, lambda : locator.locateResponder(b"simple"))
        result = normalResponderObject(amp.Box(greeting=b"ni hao", cookie=b"5"))
        def done(values):
            self.assertEqual(values, amp.AmpBox(cookieplus=b'8'))
        return result.addCallback(done)


    def test_lookupFunctionDeprecatedInvoke(self):
        """
        Invoking locateResponder under its old name, lookupFunction, should
        emit a deprecation warning, but do the same thing.
        """
        locator = TestLocator()
        responderCallable = self.assertWarns(
            PendingDeprecationWarning,
            "Call locateResponder, not lookupFunction.", __file__,
            lambda : locator.lookupFunction(b"simple"))
        result = responderCallable(amp.Box(greeting=b"ni hao", cookie=b"5"))
        def done(values):
            self.assertEqual(values, amp.AmpBox(cookieplus=b'8'))
        return result.addCallback(done)



SWITCH_CLIENT_DATA = b'Success!'
SWITCH_SERVER_DATA = b'No, really.  Success.'


class BinaryProtocolTests(unittest.TestCase):
    """
    Tests for L{amp.BinaryBoxProtocol}.

    @ivar _boxSender: After C{startReceivingBoxes} is called, the L{IBoxSender}
        which was passed to it.
    """

    def setUp(self):
        """
        Keep track of all boxes received by this test in its capacity as an
        L{IBoxReceiver} implementor.
        """
        self.boxes = []
        self.data = []


    def startReceivingBoxes(self, sender):
        """
        Implement L{IBoxReceiver.startReceivingBoxes} to just remember the
        value passed in.
        """
        self._boxSender = sender


    def ampBoxReceived(self, box):
        """
        A box was received by the protocol.
        """
        self.boxes.append(box)

    stopReason = None
    def stopReceivingBoxes(self, reason):
        """
        Record the reason that we stopped receiving boxes.
        """
        self.stopReason = reason


    # fake ITransport
    def getPeer(self):
        return 'no peer'


    def getHost(self):
        return 'no host'


    def write(self, data):
        self.assertIsInstance(data, bytes)
        self.data.append(data)


    def test_startReceivingBoxes(self):
        """
        When L{amp.BinaryBoxProtocol} is connected to a transport, it calls
        C{startReceivingBoxes} on its L{IBoxReceiver} with itself as the
        L{IBoxSender} parameter.
        """
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(None)
        self.assertIs(self._boxSender, protocol)


    def test_sendBoxInStartReceivingBoxes(self):
        """
        The L{IBoxReceiver} which is started when L{amp.BinaryBoxProtocol} is
        connected to a transport can call C{sendBox} on the L{IBoxSender}
        passed to it before C{startReceivingBoxes} returns and have that box
        sent.
        """
        class SynchronouslySendingReceiver:
            def startReceivingBoxes(self, sender):
                sender.sendBox(amp.Box({b'foo': b'bar'}))

        transport = StringTransport()
        protocol = amp.BinaryBoxProtocol(SynchronouslySendingReceiver())
        protocol.makeConnection(transport)
        self.assertEqual(
            transport.value(),
            b'\x00\x03foo\x00\x03bar\x00\x00')


    def test_receiveBoxStateMachine(self):
        """
        When a binary box protocol receives:
            * a key
            * a value
            * an empty string
        it should emit a box and send it to its boxReceiver.
        """
        a = amp.BinaryBoxProtocol(self)
        a.stringReceived(b"hello")
        a.stringReceived(b"world")
        a.stringReceived(b"")
        self.assertEqual(self.boxes, [amp.AmpBox(hello=b"world")])


    def test_firstBoxFirstKeyExcessiveLength(self):
        """
        L{amp.BinaryBoxProtocol} drops its connection if the length prefix for
        the first a key it receives is larger than 255.
        """
        transport = StringTransport()
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(transport)
        protocol.dataReceived(b'\x01\x00')
        self.assertTrue(transport.disconnecting)


    def test_firstBoxSubsequentKeyExcessiveLength(self):
        """
        L{amp.BinaryBoxProtocol} drops its connection if the length prefix for
        a subsequent key in the first box it receives is larger than 255.
        """
        transport = StringTransport()
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(transport)
        protocol.dataReceived(b'\x00\x01k\x00\x01v')
        self.assertFalse(transport.disconnecting)
        protocol.dataReceived(b'\x01\x00')
        self.assertTrue(transport.disconnecting)


    def test_subsequentBoxFirstKeyExcessiveLength(self):
        """
        L{amp.BinaryBoxProtocol} drops its connection if the length prefix for
        the first key in a subsequent box it receives is larger than 255.
        """
        transport = StringTransport()
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(transport)
        protocol.dataReceived(b'\x00\x01k\x00\x01v\x00\x00')
        self.assertFalse(transport.disconnecting)
        protocol.dataReceived(b'\x01\x00')
        self.assertTrue(transport.disconnecting)


    def test_excessiveKeyFailure(self):
        """
        If L{amp.BinaryBoxProtocol} disconnects because it received a key
        length prefix which was too large, the L{IBoxReceiver}'s
        C{stopReceivingBoxes} method is called with a L{TooLong} failure.
        """
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(StringTransport())
        protocol.dataReceived(b'\x01\x00')
        protocol.connectionLost(
            Failure(error.ConnectionDone("simulated connection done")))
        self.stopReason.trap(amp.TooLong)
        self.assertTrue(self.stopReason.value.isKey)
        self.assertFalse(self.stopReason.value.isLocal)
        self.assertIsNone(self.stopReason.value.value)
        self.assertIsNone(self.stopReason.value.keyName)


    def test_unhandledErrorWithTransport(self):
        """
        L{amp.BinaryBoxProtocol.unhandledError} logs the failure passed to it
        and disconnects its transport.
        """
        transport = StringTransport()
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(transport)
        protocol.unhandledError(Failure(RuntimeError("Fake error")))
        self.assertEqual(1, len(self.flushLoggedErrors(RuntimeError)))
        self.assertTrue(transport.disconnecting)


    def test_unhandledErrorWithoutTransport(self):
        """
        L{amp.BinaryBoxProtocol.unhandledError} completes without error when
        there is no associated transport.
        """
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(StringTransport())
        protocol.connectionLost(Failure(Exception("Simulated")))
        protocol.unhandledError(Failure(RuntimeError("Fake error")))
        self.assertEqual(1, len(self.flushLoggedErrors(RuntimeError)))


    def test_receiveBoxData(self):
        """
        When a binary box protocol receives the serialized form of an AMP box,
        it should emit a similar box to its boxReceiver.
        """
        a = amp.BinaryBoxProtocol(self)
        a.dataReceived(amp.Box({b"testKey": b"valueTest",
                                b"anotherKey": b"anotherValue"}).serialize())
        self.assertEqual(self.boxes,
                          [amp.Box({b"testKey": b"valueTest",
                                    b"anotherKey": b"anotherValue"})])


    def test_receiveLongerBoxData(self):
        """
        An L{amp.BinaryBoxProtocol} can receive serialized AMP boxes with
        values of up to (2 ** 16 - 1) bytes.
        """
        length = (2 ** 16 - 1)
        value = b'x' * length
        transport = StringTransport()
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(transport)
        protocol.dataReceived(amp.Box({'k': value}).serialize())
        self.assertEqual(self.boxes, [amp.Box({'k': value})])
        self.assertFalse(transport.disconnecting)


    def test_sendBox(self):
        """
        When a binary box protocol sends a box, it should emit the serialized
        bytes of that box to its transport.
        """
        a = amp.BinaryBoxProtocol(self)
        a.makeConnection(self)
        aBox = amp.Box({b"testKey": b"valueTest",
                        b"someData": b"hello"})
        a.makeConnection(self)
        a.sendBox(aBox)
        self.assertEqual(b''.join(self.data), aBox.serialize())


    def test_connectionLostStopSendingBoxes(self):
        """
        When a binary box protocol loses its connection, it should notify its
        box receiver that it has stopped receiving boxes.
        """
        a = amp.BinaryBoxProtocol(self)
        a.makeConnection(self)
        connectionFailure = Failure(RuntimeError())
        a.connectionLost(connectionFailure)
        self.assertIs(self.stopReason, connectionFailure)


    def test_protocolSwitch(self):
        """
        L{BinaryBoxProtocol} has the capacity to switch to a different protocol
        on a box boundary.  When a protocol is in the process of switching, it
        cannot receive traffic.
        """
        otherProto = TestProto(None, b"outgoing data")
        test = self
        class SwitchyReceiver:
            switched = False
            def startReceivingBoxes(self, sender):
                pass
            def ampBoxReceived(self, box):
                test.assertFalse(self.switched,
                                 "Should only receive one box!")
                self.switched = True
                a._lockForSwitch()
                a._switchTo(otherProto)
        a = amp.BinaryBoxProtocol(SwitchyReceiver())
        anyOldBox = amp.Box({b"include": b"lots",
                             b"of": b"data"})
        a.makeConnection(self)
        # Include a 0-length box at the beginning of the next protocol's data,
        # to make sure that AMP doesn't eat the data or try to deliver extra
        # boxes either...
        moreThanOneBox = anyOldBox.serialize() + b"\x00\x00Hello, world!"
        a.dataReceived(moreThanOneBox)
        self.assertIs(otherProto.transport, self)
        self.assertEqual(b"".join(otherProto.data), b"\x00\x00Hello, world!")
        self.assertEqual(self.data, [b"outgoing data"])
        a.dataReceived(b"more data")
        self.assertEqual(b"".join(otherProto.data),
                          b"\x00\x00Hello, world!more data")
        self.assertRaises(amp.ProtocolSwitched, a.sendBox, anyOldBox)


    def test_protocolSwitchEmptyBuffer(self):
        """
        After switching to a different protocol, if no extra bytes beyond
        the switch box were delivered, an empty string is not passed to the
        switched protocol's C{dataReceived} method.
        """
        a = amp.BinaryBoxProtocol(self)
        a.makeConnection(self)
        otherProto = TestProto(None, b"")
        a._switchTo(otherProto)
        self.assertEqual(otherProto.data, [])


    def test_protocolSwitchInvalidStates(self):
        """
        In order to make sure the protocol never gets any invalid data sent
        into the middle of a box, it must be locked for switching before it is
        switched.  It can only be unlocked if the switch failed, and attempting
        to send a box while it is locked should raise an exception.
        """
        a = amp.BinaryBoxProtocol(self)
        a.makeConnection(self)
        sampleBox = amp.Box({b"some": b"data"})
        a._lockForSwitch()
        self.assertRaises(amp.ProtocolSwitched, a.sendBox, sampleBox)
        a._unlockFromSwitch()
        a.sendBox(sampleBox)
        self.assertEqual(b''.join(self.data), sampleBox.serialize())
        a._lockForSwitch()
        otherProto = TestProto(None, b"outgoing data")
        a._switchTo(otherProto)
        self.assertRaises(amp.ProtocolSwitched, a._unlockFromSwitch)


    def test_protocolSwitchLoseConnection(self):
        """
        When the protocol is switched, it should notify its nested protocol of
        disconnection.
        """
        class Loser(protocol.Protocol):
            reason = None
            def connectionLost(self, reason):
                self.reason = reason
        connectionLoser = Loser()
        a = amp.BinaryBoxProtocol(self)
        a.makeConnection(self)
        a._lockForSwitch()
        a._switchTo(connectionLoser)
        connectionFailure = Failure(RuntimeError())
        a.connectionLost(connectionFailure)
        self.assertEqual(connectionLoser.reason, connectionFailure)


    def test_protocolSwitchLoseClientConnection(self):
        """
        When the protocol is switched, it should notify its nested client
        protocol factory of disconnection.
        """
        class ClientLoser:
            reason = None
            def clientConnectionLost(self, connector, reason):
                self.reason = reason
        a = amp.BinaryBoxProtocol(self)
        connectionLoser = protocol.Protocol()
        clientLoser = ClientLoser()
        a.makeConnection(self)
        a._lockForSwitch()
        a._switchTo(connectionLoser, clientLoser)
        connectionFailure = Failure(RuntimeError())
        a.connectionLost(connectionFailure)
        self.assertEqual(clientLoser.reason, connectionFailure)



class AMPTests(unittest.TestCase):

    def test_interfaceDeclarations(self):
        """
        The classes in the amp module ought to implement the interfaces that
        are declared for their benefit.
        """
        for interface, implementation in [(amp.IBoxSender, amp.BinaryBoxProtocol),
                                          (amp.IBoxReceiver, amp.BoxDispatcher),
                                          (amp.IResponderLocator, amp.CommandLocator),
                                          (amp.IResponderLocator, amp.SimpleStringLocator),
                                          (amp.IBoxSender, amp.AMP),
                                          (amp.IBoxReceiver, amp.AMP),
                                          (amp.IResponderLocator, amp.AMP)]:
            self.assertTrue(interface.implementedBy(implementation),
                            "%s does not implements(%s)" % (implementation, interface))


    def test_helloWorld(self):
        """
        Verify that a simple command can be sent and its response received with
        the simple low-level string-based API.
        """
        c, s, p = connectedServerAndClient()
        L = []
        HELLO = b'world'
        c.sendHello(HELLO).addCallback(L.append)
        p.flush()
        self.assertEqual(L[0][b'hello'], HELLO)


    def test_wireFormatRoundTrip(self):
        """
        Verify that mixed-case, underscored and dashed arguments are mapped to
        their python names properly.
        """
        c, s, p = connectedServerAndClient()
        L = []
        HELLO = b'world'
        c.sendHello(HELLO).addCallback(L.append)
        p.flush()
        self.assertEqual(L[0][b'hello'], HELLO)


    def test_helloWorldUnicode(self):
        """
        Verify that unicode arguments can be encoded and decoded.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        HELLO = b'world'
        HELLO_UNICODE = u'wor\u1234ld'
        c.sendUnicodeHello(HELLO, HELLO_UNICODE).addCallback(L.append)
        p.flush()
        self.assertEqual(L[0]['hello'], HELLO)
        self.assertEqual(L[0]['Print'], HELLO_UNICODE)


    def test_callRemoteStringRequiresAnswerFalse(self):
        """
        L{BoxDispatcher.callRemoteString} returns L{None} if C{requiresAnswer}
        is C{False}.
        """
        c, s, p = connectedServerAndClient()
        ret = c.callRemoteString(b"WTF", requiresAnswer=False)
        self.assertIsNone(ret)


    def test_unknownCommandLow(self):
        """
        Verify that unknown commands using low-level APIs will be rejected with an
        error, but will NOT terminate the connection.
        """
        c, s, p = connectedServerAndClient()
        L = []
        def clearAndAdd(e):
            """
            You can't propagate the error...
            """
            e.trap(amp.UnhandledCommand)
            return "OK"
        c.callRemoteString(b"WTF").addErrback(clearAndAdd).addCallback(L.append)
        p.flush()
        self.assertEqual(L.pop(), "OK")
        HELLO = b'world'
        c.sendHello(HELLO).addCallback(L.append)
        p.flush()
        self.assertEqual(L[0][b'hello'], HELLO)


    def test_unknownCommandHigh(self):
        """
        Verify that unknown commands using high-level APIs will be rejected with an
        error, but will NOT terminate the connection.
        """
        c, s, p = connectedServerAndClient()
        L = []
        def clearAndAdd(e):
            """
            You can't propagate the error...
            """
            e.trap(amp.UnhandledCommand)
            return "OK"
        c.callRemote(WTF).addErrback(clearAndAdd).addCallback(L.append)
        p.flush()
        self.assertEqual(L.pop(), "OK")
        HELLO = b'world'
        c.sendHello(HELLO).addCallback(L.append)
        p.flush()
        self.assertEqual(L[0][b'hello'], HELLO)


    def test_brokenReturnValue(self):
        """
        It can be very confusing if you write some code which responds to a
        command, but gets the return value wrong.  Most commonly you end up
        returning None instead of a dictionary.

        Verify that if that happens, the framework logs a useful error.
        """
        L = []
        SimpleSymmetricCommandProtocol().dispatchCommand(
            amp.AmpBox(_command=BrokenReturn.commandName)).addErrback(L.append)
        L[0].trap(amp.BadLocalReturn)
        self.failUnlessIn('None', repr(L[0].value))


    def test_unknownArgument(self):
        """
        Verify that unknown arguments are ignored, and not passed to a Python
        function which can't accept them.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        HELLO = b'world'
        # c.sendHello(HELLO).addCallback(L.append)
        c.callRemote(FutureHello,
                     hello=HELLO,
                     bonus=b"I'm not in the book!").addCallback(
            L.append)
        p.flush()
        self.assertEqual(L[0]['hello'], HELLO)


    def test_simpleReprs(self):
        """
        Verify that the various Box objects repr properly, for debugging.
        """
        self.assertEqual(type(repr(amp._SwitchBox('a'))), str)
        self.assertEqual(type(repr(amp.QuitBox())), str)
        self.assertEqual(type(repr(amp.AmpBox())), str)
        self.assertIn("AmpBox", repr(amp.AmpBox()))


    def test_innerProtocolInRepr(self):
        """
        Verify that L{AMP} objects output their innerProtocol when set.
        """
        otherProto = TestProto(None, b"outgoing data")
        a = amp.AMP()
        a.innerProtocol = otherProto

        self.assertEqual(
            repr(a), "<AMP inner <TestProto #%d> at 0x%x>" % (
                otherProto.instanceId, id(a)))


    def test_innerProtocolNotInRepr(self):
        """
        Verify that L{AMP} objects do not output 'inner' when no innerProtocol
        is set.
        """
        a = amp.AMP()
        self.assertEqual(repr(a), "<AMP at 0x%x>" % (id(a),))


    def test_simpleSSLRepr(self):
        """
        L{amp._TLSBox.__repr__} returns a string.
        """
        self.assertEqual(type(repr(amp._TLSBox())), str)

    test_simpleSSLRepr.skip = skipSSL


    def test_keyTooLong(self):
        """
        Verify that a key that is too long will immediately raise a synchronous
        exception.
        """
        c, s, p = connectedServerAndClient()
        x = "H" * (0xff+1)
        tl = self.assertRaises(amp.TooLong,
                               c.callRemoteString, b"Hello",
                               **{x: b"hi"})
        self.assertTrue(tl.isKey)
        self.assertTrue(tl.isLocal)
        self.assertIsNone(tl.keyName)
        self.assertEqual(tl.value, x.encode("ascii"))
        self.assertIn(str(len(x)), repr(tl))
        self.assertIn("key", repr(tl))


    def test_valueTooLong(self):
        """
        Verify that attempting to send value longer than 64k will immediately
        raise an exception.
        """
        c, s, p = connectedServerAndClient()
        x = b"H" * (0xffff+1)
        tl = self.assertRaises(amp.TooLong, c.sendHello, x)
        p.flush()
        self.assertFalse(tl.isKey)
        self.assertTrue(tl.isLocal)
        self.assertEqual(tl.keyName, b'hello')
        self.failUnlessIdentical(tl.value, x)
        self.assertIn(str(len(x)), repr(tl))
        self.assertIn("value", repr(tl))
        self.assertIn('hello', repr(tl))


    def test_helloWorldCommand(self):
        """
        Verify that a simple command can be sent and its response received with
        the high-level value parsing API.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        HELLO = b'world'
        c.sendHello(HELLO).addCallback(L.append)
        p.flush()
        self.assertEqual(L[0]['hello'], HELLO)


    def test_helloErrorHandling(self):
        """
        Verify that if a known error type is raised and handled, it will be
        properly relayed to the other end of the connection and translated into
        an exception, and no error will be logged.
        """
        L=[]
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        HELLO = b'fuck you'
        c.sendHello(HELLO).addErrback(L.append)
        p.flush()
        L[0].trap(UnfriendlyGreeting)
        self.assertEqual(str(L[0].value), "Don't be a dick.")


    def test_helloFatalErrorHandling(self):
        """
        Verify that if a known, fatal error type is raised and handled, it will
        be properly relayed to the other end of the connection and translated
        into an exception, no error will be logged, and the connection will be
        terminated.
        """
        L=[]
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        HELLO = b'die'
        c.sendHello(HELLO).addErrback(L.append)
        p.flush()
        L.pop().trap(DeathThreat)
        c.sendHello(HELLO).addErrback(L.append)
        p.flush()
        L.pop().trap(error.ConnectionDone)



    def test_helloNoErrorHandling(self):
        """
        Verify that if an unknown error type is raised, it will be relayed to
        the other end of the connection and translated into an exception, it
        will be logged, and then the connection will be dropped.
        """
        L=[]
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        HELLO = THING_I_DONT_UNDERSTAND
        c.sendHello(HELLO).addErrback(L.append)
        p.flush()
        ure = L.pop()
        ure.trap(amp.UnknownRemoteError)
        c.sendHello(HELLO).addErrback(L.append)
        cl = L.pop()
        cl.trap(error.ConnectionDone)
        # The exception should have been logged.
        self.assertTrue(self.flushLoggedErrors(ThingIDontUnderstandError))



    def test_lateAnswer(self):
        """
        Verify that a command that does not get answered until after the
        connection terminates will not cause any errors.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        c.callRemote(WaitForever).addErrback(L.append)
        p.flush()
        self.assertEqual(L, [])
        s.transport.loseConnection()
        p.flush()
        L.pop().trap(error.ConnectionDone)
        # Just make sure that it doesn't error...
        s.waiting.callback({})
        return s.waiting


    def test_requiresNoAnswer(self):
        """
        Verify that a command that requires no answer is run.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        HELLO = b'world'
        c.callRemote(NoAnswerHello, hello=HELLO)
        p.flush()
        self.assertTrue(s.greeted)


    def test_requiresNoAnswerFail(self):
        """
        Verify that commands sent after a failed no-answer request do not complete.
        """
        L=[]
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        HELLO = b'fuck you'
        c.callRemote(NoAnswerHello, hello=HELLO)
        p.flush()
        # This should be logged locally.
        self.assertTrue(self.flushLoggedErrors(amp.RemoteAmpError))
        HELLO = b'world'
        c.callRemote(Hello, hello=HELLO).addErrback(L.append)
        p.flush()
        L.pop().trap(error.ConnectionDone)
        self.assertFalse(s.greeted)


    def test_noAnswerResponderBadAnswer(self):
        """
        Verify that responders of requiresAnswer=False commands have to return
        a dictionary anyway.

        (requiresAnswer is a hint from the _client_ - the server may be called
        upon to answer commands in any case, if the client wants to know when
        they complete.)
        """
        c, s, p = connectedServerAndClient(
            ServerClass=BadNoAnswerCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        c.callRemote(NoAnswerHello, hello=b"hello")
        p.flush()
        le = self.flushLoggedErrors(amp.BadLocalReturn)
        self.assertEqual(len(le), 1)


    def test_noAnswerResponderAskedForAnswer(self):
        """
        Verify that responders with requiresAnswer=False will actually respond
        if the client sets requiresAnswer=True.  In other words, verify that
        requiresAnswer is a hint honored only by the client.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=NoAnswerCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        c.callRemote(Hello, hello=b"Hello!").addCallback(L.append)
        p.flush()
        self.assertEqual(len(L), 1)
        self.assertEqual(L, [dict(hello=b"Hello!-noanswer",
                                   Print=None)])  # Optional response argument


    def test_ampListCommand(self):
        """
        Test encoding of an argument that uses the AmpList encoding.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        c.callRemote(GetList, length=10).addCallback(L.append)
        p.flush()
        values = L.pop().get('body')
        self.assertEqual(values, [{'x': 1}] * 10)


    def test_optionalAmpListOmitted(self):
        """
        Sending a command with an omitted AmpList argument that is
        designated as optional does not raise an InvalidSignature error.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        c.callRemote(DontRejectMe, magicWord=u'please').addCallback(L.append)
        p.flush()
        response = L.pop().get('response')
        self.assertEqual(response, 'list omitted')


    def test_optionalAmpListPresent(self):
        """
        Sanity check that optional AmpList arguments are processed normally.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        c.callRemote(DontRejectMe, magicWord=u'please',
                list=[{'name': u'foo'}]).addCallback(L.append)
        p.flush()
        response = L.pop().get('response')
        self.assertEqual(response, 'foo accepted')


    def test_failEarlyOnArgSending(self):
        """
        Verify that if we pass an invalid argument list (omitting an argument),
        an exception will be raised.
        """
        self.assertRaises(amp.InvalidSignature, Hello)


    def test_doubleProtocolSwitch(self):
        """
        As a debugging aid, a protocol system should raise a
        L{ProtocolSwitched} exception when asked to switch a protocol that is
        already switched.
        """
        serverDeferred = defer.Deferred()
        serverProto = SimpleSymmetricCommandProtocol(serverDeferred)
        clientDeferred = defer.Deferred()
        clientProto = SimpleSymmetricCommandProtocol(clientDeferred)
        c, s, p = connectedServerAndClient(ServerClass=lambda: serverProto,
                                           ClientClass=lambda: clientProto)
        def switched(result):
            self.assertRaises(amp.ProtocolSwitched, c.switchToTestProtocol)
            self.testSucceeded = True
        c.switchToTestProtocol().addCallback(switched)
        p.flush()
        self.assertTrue(self.testSucceeded)


    def test_protocolSwitch(self, switcher=SimpleSymmetricCommandProtocol,
                            spuriousTraffic=False,
                            spuriousError=False):
        """
        Verify that it is possible to switch to another protocol mid-connection and
        send data to it successfully.
        """
        self.testSucceeded = False

        serverDeferred = defer.Deferred()
        serverProto = switcher(serverDeferred)
        clientDeferred = defer.Deferred()
        clientProto = switcher(clientDeferred)
        c, s, p = connectedServerAndClient(ServerClass=lambda: serverProto,
                                           ClientClass=lambda: clientProto)

        if spuriousTraffic:
            wfdr = []           # remote
            c.callRemote(WaitForever).addErrback(wfdr.append)
        switchDeferred = c.switchToTestProtocol()
        if spuriousTraffic:
            self.assertRaises(amp.ProtocolSwitched, c.sendHello, b'world')

        def cbConnsLost(info):
            ((serverSuccess, serverData), (clientSuccess, clientData)) = info
            self.assertTrue(serverSuccess)
            self.assertTrue(clientSuccess)
            self.assertEqual(b''.join(serverData), SWITCH_CLIENT_DATA)
            self.assertEqual(b''.join(clientData), SWITCH_SERVER_DATA)
            self.testSucceeded = True

        def cbSwitch(proto):
            return defer.DeferredList(
                [serverDeferred, clientDeferred]).addCallback(cbConnsLost)

        switchDeferred.addCallback(cbSwitch)
        p.flush()
        if serverProto.maybeLater is not None:
            serverProto.maybeLater.callback(serverProto.maybeLaterProto)
            p.flush()
        if spuriousTraffic:
            # switch is done here; do this here to make sure that if we're
            # going to corrupt the connection, we do it before it's closed.
            if spuriousError:
                s.waiting.errback(amp.RemoteAmpError(
                        b"SPURIOUS",
                        "Here's some traffic in the form of an error."))
            else:
                s.waiting.callback({})
            p.flush()
        c.transport.loseConnection() # close it
        p.flush()
        self.assertTrue(self.testSucceeded)


    def test_protocolSwitchDeferred(self):
        """
        Verify that protocol-switching even works if the value returned from
        the command that does the switch is deferred.
        """
        return self.test_protocolSwitch(switcher=DeferredSymmetricCommandProtocol)


    def test_protocolSwitchFail(self, switcher=SimpleSymmetricCommandProtocol):
        """
        Verify that if we try to switch protocols and it fails, the connection
        stays up and we can go back to speaking AMP.
        """
        self.testSucceeded = False

        serverDeferred = defer.Deferred()
        serverProto = switcher(serverDeferred)
        clientDeferred = defer.Deferred()
        clientProto = switcher(clientDeferred)
        c, s, p = connectedServerAndClient(ServerClass=lambda: serverProto,
                                           ClientClass=lambda: clientProto)
        L = []
        c.switchToTestProtocol(fail=True).addErrback(L.append)
        p.flush()
        L.pop().trap(UnknownProtocol)
        self.assertFalse(self.testSucceeded)
        # It's a known error, so let's send a "hello" on the same connection;
        # it should work.
        c.sendHello(b'world').addCallback(L.append)
        p.flush()
        self.assertEqual(L.pop()['hello'], b'world')


    def test_trafficAfterSwitch(self):
        """
        Verify that attempts to send traffic after a switch will not corrupt
        the nested protocol.
        """
        return self.test_protocolSwitch(spuriousTraffic=True)


    def test_errorAfterSwitch(self):
        """
        Returning an error after a protocol switch should record the underlying
        error.
        """
        return self.test_protocolSwitch(spuriousTraffic=True,
                                        spuriousError=True)


    def test_quitBoxQuits(self):
        """
        Verify that commands with a responseType of QuitBox will in fact
        terminate the connection.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)

        L = []
        HELLO = b'world'
        GOODBYE = b'everyone'
        c.sendHello(HELLO).addCallback(L.append)
        p.flush()
        self.assertEqual(L.pop()['hello'], HELLO)
        c.callRemote(Goodbye).addCallback(L.append)
        p.flush()
        self.assertEqual(L.pop()['goodbye'], GOODBYE)
        c.sendHello(HELLO).addErrback(L.append)
        L.pop().trap(error.ConnectionDone)


    def test_basicLiteralEmit(self):
        """
        Verify that the command dictionaries for a callRemoteN look correct
        after being serialized and parsed.
        """
        c, s, p = connectedServerAndClient()
        L = []
        s.ampBoxReceived = L.append
        c.callRemote(Hello, hello=b'hello test', mixedCase=b'mixed case arg test',
                     dash_arg=b'x', underscore_arg=b'y')
        p.flush()
        self.assertEqual(len(L), 1)
        for k, v in [(b'_command', Hello.commandName),
                     (b'hello', b'hello test'),
                     (b'mixedCase', b'mixed case arg test'),
                     (b'dash-arg', b'x'),
                     (b'underscore_arg', b'y')]:
            self.assertEqual(L[-1].pop(k), v)
        L[-1].pop(b'_ask')
        self.assertEqual(L[-1], {})


    def test_basicStructuredEmit(self):
        """
        Verify that a call similar to basicLiteralEmit's is handled properly with
        high-level quoting and passing to Python methods, and that argument
        names are correctly handled.
        """
        L = []
        class StructuredHello(amp.AMP):
            def h(self, *a, **k):
                L.append((a, k))
                return dict(hello=b'aaa')
            Hello.responder(h)
        c, s, p = connectedServerAndClient(ServerClass=StructuredHello)
        c.callRemote(Hello, hello=b'hello test', mixedCase=b'mixed case arg test',
                     dash_arg=b'x', underscore_arg=b'y').addCallback(L.append)
        p.flush()
        self.assertEqual(len(L), 2)
        self.assertEqual(L[0],
                          ((), dict(
                    hello=b'hello test',
                    mixedCase=b'mixed case arg test',
                    dash_arg=b'x',
                    underscore_arg=b'y',
                    From=s.transport.getPeer(),

                    # XXX - should optional arguments just not be passed?
                    # passing None seems a little odd, looking at the way it
                    # turns out here... -glyph
                    Print=None,
                    optional=None,
                    )))
        self.assertEqual(L[1], dict(Print=None, hello=b'aaa'))

class PretendRemoteCertificateAuthority:
    def checkIsPretendRemote(self):
        return True

class IOSimCert:
    verifyCount = 0

    def options(self, *ign):
        return self

    def iosimVerify(self, otherCert):
        """
        This isn't a real certificate, and wouldn't work on a real socket, but
        iosim specifies a different API so that we don't have to do any crypto
        math to demonstrate that the right functions get called in the right
        places.
        """
        assert otherCert is self
        self.verifyCount += 1
        return True

class OKCert(IOSimCert):
    def options(self, x):
        assert x.checkIsPretendRemote()
        return self

class GrumpyCert(IOSimCert):
    def iosimVerify(self, otherCert):
        self.verifyCount += 1
        return False

class DroppyCert(IOSimCert):
    def __init__(self, toDrop):
        self.toDrop = toDrop

    def iosimVerify(self, otherCert):
        self.verifyCount += 1
        self.toDrop.loseConnection()
        return True

class SecurableProto(FactoryNotifier):

    factory = None

    def verifyFactory(self):
        return [PretendRemoteCertificateAuthority()]

    def getTLSVars(self):
        cert = self.certFactory()
        verify = self.verifyFactory()
        return dict(
            tls_localCertificate=cert,
            tls_verifyAuthorities=verify)
    amp.StartTLS.responder(getTLSVars)



class TLSTests(unittest.TestCase):
    def test_startingTLS(self):
        """
        Verify that starting TLS and succeeding at handshaking sends all the
        notifications to all the right places.
        """
        cli, svr, p = connectedServerAndClient(
            ServerClass=SecurableProto,
            ClientClass=SecurableProto)

        okc = OKCert()
        svr.certFactory = lambda : okc

        cli.callRemote(
            amp.StartTLS, tls_localCertificate=okc,
            tls_verifyAuthorities=[PretendRemoteCertificateAuthority()])

        # let's buffer something to be delivered securely
        L = []
        cli.callRemote(SecuredPing).addCallback(L.append)
        p.flush()
        # once for client once for server
        self.assertEqual(okc.verifyCount, 2)
        L = []
        cli.callRemote(SecuredPing).addCallback(L.append)
        p.flush()
        self.assertEqual(L[0], {'pinged': True})


    def test_startTooManyTimes(self):
        """
        Verify that the protocol will complain if we attempt to renegotiate TLS,
        which we don't support.
        """
        cli, svr, p = connectedServerAndClient(
            ServerClass=SecurableProto,
            ClientClass=SecurableProto)

        okc = OKCert()
        svr.certFactory = lambda : okc

        cli.callRemote(amp.StartTLS,
                       tls_localCertificate=okc,
                       tls_verifyAuthorities=[PretendRemoteCertificateAuthority()])
        p.flush()
        cli.noPeerCertificate = True # this is totally fake
        self.assertRaises(
            amp.OnlyOneTLS,
            cli.callRemote,
            amp.StartTLS,
            tls_localCertificate=okc,
            tls_verifyAuthorities=[PretendRemoteCertificateAuthority()])


    def test_negotiationFailed(self):
        """
        Verify that starting TLS and failing on both sides at handshaking sends
        notifications to all the right places and terminates the connection.
        """

        badCert = GrumpyCert()

        cli, svr, p = connectedServerAndClient(
            ServerClass=SecurableProto,
            ClientClass=SecurableProto)
        svr.certFactory = lambda : badCert

        cli.callRemote(amp.StartTLS,
                       tls_localCertificate=badCert)

        p.flush()
        # once for client once for server - but both fail
        self.assertEqual(badCert.verifyCount, 2)
        d = cli.callRemote(SecuredPing)
        p.flush()
        self.assertFailure(d, iosim.NativeOpenSSLError)


    def test_negotiationFailedByClosing(self):
        """
        Verify that starting TLS and failing by way of a lost connection
        notices that it is probably an SSL problem.
        """

        cli, svr, p = connectedServerAndClient(
            ServerClass=SecurableProto,
            ClientClass=SecurableProto)
        droppyCert = DroppyCert(svr.transport)
        svr.certFactory = lambda : droppyCert

        cli.callRemote(amp.StartTLS, tls_localCertificate=droppyCert)

        p.flush()

        self.assertEqual(droppyCert.verifyCount, 2)

        d = cli.callRemote(SecuredPing)
        p.flush()

        # it might be a good idea to move this exception somewhere more
        # reasonable.
        self.assertFailure(d, error.PeerVerifyError)

    skip = skipSSL



class TLSNotAvailableTests(unittest.TestCase):
    """
    Tests what happened when ssl is not available in current installation.
    """

    def setUp(self):
        """
        Disable ssl in amp.
        """
        self.ssl = amp.ssl
        amp.ssl = None


    def tearDown(self):
        """
        Restore ssl module.
        """
        amp.ssl = self.ssl


    def test_callRemoteError(self):
        """
        Check that callRemote raises an exception when called with a
        L{amp.StartTLS}.
        """
        cli, svr, p = connectedServerAndClient(
            ServerClass=SecurableProto,
            ClientClass=SecurableProto)

        okc = OKCert()
        svr.certFactory = lambda : okc

        return self.assertFailure(cli.callRemote(
            amp.StartTLS, tls_localCertificate=okc,
            tls_verifyAuthorities=[PretendRemoteCertificateAuthority()]),
            RuntimeError)


    def test_messageReceivedError(self):
        """
        When a client with SSL enabled talks to a server without SSL, it
        should return a meaningful error.
        """
        svr = SecurableProto()
        okc = OKCert()
        svr.certFactory = lambda : okc
        box = amp.Box()
        box[b'_command'] = b'StartTLS'
        box[b'_ask'] = b'1'
        boxes = []
        svr.sendBox = boxes.append
        svr.makeConnection(StringTransport())
        svr.ampBoxReceived(box)
        self.assertEqual(boxes,
            [{b'_error_code': b'TLS_ERROR',
              b'_error': b'1',
              b'_error_description': b'TLS not available'}])



class InheritedError(Exception):
    """
    This error is used to check inheritance.
    """



class OtherInheritedError(Exception):
    """
    This is a distinct error for checking inheritance.
    """



class BaseCommand(amp.Command):
    """
    This provides a command that will be subclassed.
    """
    errors = {InheritedError: b'INHERITED_ERROR'}



class InheritedCommand(BaseCommand):
    """
    This is a command which subclasses another command but does not override
    anything.
    """



class AddErrorsCommand(BaseCommand):
    """
    This is a command which subclasses another command but adds errors to the
    list.
    """
    arguments = [(b'other', amp.Boolean())]
    errors = {OtherInheritedError: b'OTHER_INHERITED_ERROR'}



class NormalCommandProtocol(amp.AMP):
    """
    This is a protocol which responds to L{BaseCommand}, and is used to test
    that inheritance does not interfere with the normal handling of errors.
    """
    def resp(self):
        raise InheritedError()
    BaseCommand.responder(resp)



class InheritedCommandProtocol(amp.AMP):
    """
    This is a protocol which responds to L{InheritedCommand}, and is used to
    test that inherited commands inherit their bases' errors if they do not
    respond to any of their own.
    """
    def resp(self):
        raise InheritedError()
    InheritedCommand.responder(resp)



class AddedCommandProtocol(amp.AMP):
    """
    This is a protocol which responds to L{AddErrorsCommand}, and is used to
    test that inherited commands can add their own new types of errors, but
    still respond in the same way to their parents types of errors.
    """
    def resp(self, other):
        if other:
            raise OtherInheritedError()
        else:
            raise InheritedError()
    AddErrorsCommand.responder(resp)



class CommandInheritanceTests(unittest.TestCase):
    """
    These tests verify that commands inherit error conditions properly.
    """

    def errorCheck(self, err, proto, cmd, **kw):
        """
        Check that the appropriate kind of error is raised when a given command
        is sent to a given protocol.
        """
        c, s, p = connectedServerAndClient(ServerClass=proto,
                                           ClientClass=proto)
        d = c.callRemote(cmd, **kw)
        d2 = self.failUnlessFailure(d, err)
        p.flush()
        return d2


    def test_basicErrorPropagation(self):
        """
        Verify that errors specified in a superclass are respected normally
        even if it has subclasses.
        """
        return self.errorCheck(
            InheritedError, NormalCommandProtocol, BaseCommand)


    def test_inheritedErrorPropagation(self):
        """
        Verify that errors specified in a superclass command are propagated to
        its subclasses.
        """
        return self.errorCheck(
            InheritedError, InheritedCommandProtocol, InheritedCommand)


    def test_inheritedErrorAddition(self):
        """
        Verify that new errors specified in a subclass of an existing command
        are honored even if the superclass defines some errors.
        """
        return self.errorCheck(
            OtherInheritedError, AddedCommandProtocol, AddErrorsCommand, other=True)


    def test_additionWithOriginalError(self):
        """
        Verify that errors specified in a command's superclass are respected
        even if that command defines new errors itself.
        """
        return self.errorCheck(
            InheritedError, AddedCommandProtocol, AddErrorsCommand, other=False)


def _loseAndPass(err, proto):
    # be specific, pass on the error to the client.
    err.trap(error.ConnectionLost, error.ConnectionDone)
    del proto.connectionLost
    proto.connectionLost(err)


class LiveFireBase:
    """
    Utility for connected reactor-using tests.
    """

    def setUp(self):
        """
        Create an amp server and connect a client to it.
        """
        from twisted.internet import reactor
        self.serverFactory = protocol.ServerFactory()
        self.serverFactory.protocol = self.serverProto
        self.clientFactory = protocol.ClientFactory()
        self.clientFactory.protocol = self.clientProto
        self.clientFactory.onMade = defer.Deferred()
        self.serverFactory.onMade = defer.Deferred()
        self.serverPort = reactor.listenTCP(0, self.serverFactory)
        self.addCleanup(self.serverPort.stopListening)
        self.clientConn = reactor.connectTCP(
            '127.0.0.1', self.serverPort.getHost().port,
            self.clientFactory)
        self.addCleanup(self.clientConn.disconnect)
        def getProtos(rlst):
            self.cli = self.clientFactory.theProto
            self.svr = self.serverFactory.theProto
        dl = defer.DeferredList([self.clientFactory.onMade,
                                 self.serverFactory.onMade])
        return dl.addCallback(getProtos)

    def tearDown(self):
        """
        Cleanup client and server connections, and check the error got at
        C{connectionLost}.
        """
        L = []
        for conn in self.cli, self.svr:
            if conn.transport is not None:
                # depend on amp's function connection-dropping behavior
                d = defer.Deferred().addErrback(_loseAndPass, conn)
                conn.connectionLost = d.errback
                conn.transport.loseConnection()
                L.append(d)
        return defer.gatherResults(L
            ).addErrback(lambda first: first.value.subFailure)


def show(x):
    import sys
    sys.stdout.write(x+'\n')
    sys.stdout.flush()


def tempSelfSigned():
    from twisted.internet import ssl

    sharedDN = ssl.DN(CN='shared')
    key = ssl.KeyPair.generate()
    cr = key.certificateRequest(sharedDN)
    sscrd = key.signCertificateRequest(
        sharedDN, cr, lambda dn: True, 1234567)
    cert = key.newCertificate(sscrd)
    return cert

if ssl is not None:
    tempcert = tempSelfSigned()


class LiveFireTLSTests(LiveFireBase, unittest.TestCase):
    clientProto = SecurableProto
    serverProto = SecurableProto
    def test_liveFireCustomTLS(self):
        """
        Using real, live TLS, actually negotiate a connection.

        This also looks at the 'peerCertificate' attribute's correctness, since
        that's actually loaded using OpenSSL calls, but the main purpose is to
        make sure that we didn't miss anything obvious in iosim about TLS
        negotiations.
        """

        cert = tempcert

        self.svr.verifyFactory = lambda : [cert]
        self.svr.certFactory = lambda : cert
        # only needed on the server, we specify the client below.

        def secured(rslt):
            x = cert.digest()
            def pinged(rslt2):
                # Interesting.  OpenSSL won't even _tell_ us about the peer
                # cert until we negotiate.  we should be able to do this in
                # 'secured' instead, but it looks like we can't.  I think this
                # is a bug somewhere far deeper than here.
                self.assertEqual(x, self.cli.hostCertificate.digest())
                self.assertEqual(x, self.cli.peerCertificate.digest())
                self.assertEqual(x, self.svr.hostCertificate.digest())
                self.assertEqual(x, self.svr.peerCertificate.digest())
            return self.cli.callRemote(SecuredPing).addCallback(pinged)
        return self.cli.callRemote(amp.StartTLS,
                                   tls_localCertificate=cert,
                                   tls_verifyAuthorities=[cert]).addCallback(secured)

    skip = skipSSL



class SlightlySmartTLS(SimpleSymmetricCommandProtocol):
    """
    Specific implementation of server side protocol with different
    management of TLS.
    """
    def getTLSVars(self):
        """
        @return: the global C{tempcert} certificate as local certificate.
        """
        return dict(tls_localCertificate=tempcert)
    amp.StartTLS.responder(getTLSVars)


class PlainVanillaLiveFireTests(LiveFireBase, unittest.TestCase):

    clientProto = SimpleSymmetricCommandProtocol
    serverProto = SimpleSymmetricCommandProtocol

    def test_liveFireDefaultTLS(self):
        """
        Verify that out of the box, we can start TLS to at least encrypt the
        connection, even if we don't have any certificates to use.
        """
        def secured(result):
            return self.cli.callRemote(SecuredPing)
        return self.cli.callRemote(amp.StartTLS).addCallback(secured)

    skip = skipSSL



class WithServerTLSVerificationTests(LiveFireBase, unittest.TestCase):
    clientProto = SimpleSymmetricCommandProtocol
    serverProto = SlightlySmartTLS

    def test_anonymousVerifyingClient(self):
        """
        Verify that anonymous clients can verify server certificates.
        """
        def secured(result):
            return self.cli.callRemote(SecuredPing)
        return self.cli.callRemote(amp.StartTLS,
                                   tls_verifyAuthorities=[tempcert]
            ).addCallback(secured)

    skip = skipSSL



class ProtocolIncludingArgument(amp.Argument):
    """
    An L{amp.Argument} which encodes its parser and serializer
    arguments *including the protocol* into its parsed and serialized
    forms.
    """

    def fromStringProto(self, string, protocol):
        """
        Don't decode anything; just return all possible information.

        @return: A two-tuple of the input string and the protocol.
        """
        return (string, protocol)

    def toStringProto(self, obj, protocol):
        """
        Encode identifying information about L{object} and protocol
        into a string for later verification.

        @type obj: L{object}
        @type protocol: L{amp.AMP}
        """
        ident = u"%d:%d" % (id(obj), id(protocol))
        return ident.encode("ascii")



class ProtocolIncludingCommand(amp.Command):
    """
    A command that has argument and response schemas which use
    L{ProtocolIncludingArgument}.
    """
    arguments = [(b'weird', ProtocolIncludingArgument())]
    response = [(b'weird', ProtocolIncludingArgument())]



class MagicSchemaCommand(amp.Command):
    """
    A command which overrides L{parseResponse}, L{parseArguments}, and
    L{makeResponse}.
    """
    def parseResponse(self, strings, protocol):
        """
        Don't do any parsing, just jam the input strings and protocol
        onto the C{protocol.parseResponseArguments} attribute as a
        two-tuple. Return the original strings.
        """
        protocol.parseResponseArguments = (strings, protocol)
        return strings
    parseResponse = classmethod(parseResponse)


    def parseArguments(cls, strings, protocol):
        """
        Don't do any parsing, just jam the input strings and protocol
        onto the C{protocol.parseArgumentsArguments} attribute as a
        two-tuple. Return the original strings.
        """
        protocol.parseArgumentsArguments = (strings, protocol)
        return strings
    parseArguments = classmethod(parseArguments)


    def makeArguments(cls, objects, protocol):
        """
        Don't do any serializing, just jam the input strings and protocol
        onto the C{protocol.makeArgumentsArguments} attribute as a
        two-tuple. Return the original strings.
        """
        protocol.makeArgumentsArguments = (objects, protocol)
        return objects
    makeArguments = classmethod(makeArguments)



class NoNetworkProtocol(amp.AMP):
    """
    An L{amp.AMP} subclass which overrides private methods to avoid
    testing the network. It also provides a responder for
    L{MagicSchemaCommand} that does nothing, so that tests can test
    aspects of the interaction of L{amp.Command}s and L{amp.AMP}.

    @ivar parseArgumentsArguments: Arguments that have been passed to any
    L{MagicSchemaCommand}, if L{MagicSchemaCommand} has been handled by
    this protocol.

    @ivar parseResponseArguments: Responses that have been returned from a
    L{MagicSchemaCommand}, if L{MagicSchemaCommand} has been handled by
    this protocol.

    @ivar makeArgumentsArguments: Arguments that have been serialized by any
    L{MagicSchemaCommand}, if L{MagicSchemaCommand} has been handled by
    this protocol.
    """
    def _sendBoxCommand(self, commandName, strings, requiresAnswer):
        """
        Return a Deferred which fires with the original strings.
        """
        return defer.succeed(strings)

    MagicSchemaCommand.responder(lambda s, weird: {})



class MyBox(dict):
    """
    A unique dict subclass.
    """



class ProtocolIncludingCommandWithDifferentCommandType(
    ProtocolIncludingCommand):
    """
    A L{ProtocolIncludingCommand} subclass whose commandType is L{MyBox}
    """
    commandType = MyBox



class CommandTests(unittest.TestCase):
    """
    Tests for L{amp.Argument} and L{amp.Command}.
    """
    def test_argumentInterface(self):
        """
        L{Argument} instances provide L{amp.IArgumentType}.
        """
        self.assertTrue(verifyObject(amp.IArgumentType, amp.Argument()))


    def test_parseResponse(self):
        """
        There should be a class method of Command which accepts a
        mapping of argument names to serialized forms and returns a
        similar mapping whose values have been parsed via the
        Command's response schema.
        """
        protocol = object()
        result = b'whatever'
        strings = {b'weird': result}
        self.assertEqual(
            ProtocolIncludingCommand.parseResponse(strings, protocol),
            {'weird': (result, protocol)})


    def test_callRemoteCallsParseResponse(self):
        """
        Making a remote call on a L{amp.Command} subclass which
        overrides the C{parseResponse} method should call that
        C{parseResponse} method to get the response.
        """
        client = NoNetworkProtocol()
        thingy = b"weeoo"
        response = client.callRemote(MagicSchemaCommand, weird=thingy)
        def gotResponse(ign):
            self.assertEqual(client.parseResponseArguments,
                              ({"weird": thingy}, client))
        response.addCallback(gotResponse)
        return response


    def test_parseArguments(self):
        """
        There should be a class method of L{amp.Command} which accepts
        a mapping of argument names to serialized forms and returns a
        similar mapping whose values have been parsed via the
        command's argument schema.
        """
        protocol = object()
        result = b'whatever'
        strings = {b'weird': result}
        self.assertEqual(
            ProtocolIncludingCommand.parseArguments(strings, protocol),
            {'weird': (result, protocol)})


    def test_responderCallsParseArguments(self):
        """
        Making a remote call on a L{amp.Command} subclass which
        overrides the C{parseArguments} method should call that
        C{parseArguments} method to get the arguments.
        """
        protocol = NoNetworkProtocol()
        responder = protocol.locateResponder(MagicSchemaCommand.commandName)
        argument = object()
        response = responder(dict(weird=argument))
        response.addCallback(
            lambda ign: self.assertEqual(protocol.parseArgumentsArguments,
                                         ({"weird": argument}, protocol)))
        return response


    def test_makeArguments(self):
        """
        There should be a class method of L{amp.Command} which accepts
        a mapping of argument names to objects and returns a similar
        mapping whose values have been serialized via the command's
        argument schema.
        """
        protocol = object()
        argument = object()
        objects = {'weird': argument}
        ident = u"%d:%d" % (id(argument), id(protocol))
        self.assertEqual(
            ProtocolIncludingCommand.makeArguments(objects, protocol),
            {b'weird': ident.encode("ascii")})


    def test_makeArgumentsUsesCommandType(self):
        """
        L{amp.Command.makeArguments}'s return type should be the type
        of the result of L{amp.Command.commandType}.
        """
        protocol = object()
        objects = {"weird": b"whatever"}

        result = ProtocolIncludingCommandWithDifferentCommandType.makeArguments(
            objects, protocol)
        self.assertIs(type(result), MyBox)


    def test_callRemoteCallsMakeArguments(self):
        """
        Making a remote call on a L{amp.Command} subclass which
        overrides the C{makeArguments} method should call that
        C{makeArguments} method to get the response.
        """
        client = NoNetworkProtocol()
        argument = object()
        response = client.callRemote(MagicSchemaCommand, weird=argument)
        def gotResponse(ign):
            self.assertEqual(client.makeArgumentsArguments,
                             ({"weird": argument}, client))
        response.addCallback(gotResponse)
        return response


    def test_extraArgumentsDisallowed(self):
        """
        L{Command.makeArguments} raises L{amp.InvalidSignature} if the objects
        dictionary passed to it includes a key which does not correspond to the
        Python identifier for a defined argument.
        """
        self.assertRaises(
            amp.InvalidSignature,
            Hello.makeArguments,
            dict(hello="hello", bogusArgument=object()), None)


    def test_wireSpellingDisallowed(self):
        """
        If a command argument conflicts with a Python keyword, the
        untransformed argument name is not allowed as a key in the dictionary
        passed to L{Command.makeArguments}.  If it is supplied,
        L{amp.InvalidSignature} is raised.

        This may be a pointless implementation restriction which may be lifted.
        The current behavior is tested to verify that such arguments are not
        silently dropped on the floor (the previous behavior).
        """
        self.assertRaises(
            amp.InvalidSignature,
            Hello.makeArguments,
            dict(hello="required", **{"print": "print value"}),
            None)


    def test_commandNameDefaultsToClassNameAsByteString(self):
        """
        A L{Command} subclass without a defined C{commandName} that's
        not a byte string.
        """
        class NewCommand(amp.Command):
            """
            A new command.
            """

        self.assertEqual(b"NewCommand", NewCommand.commandName)


    def test_commandNameMustBeAByteString(self):
        """
        A L{Command} subclass cannot be defined with a C{commandName} that's
        not a byte string.
        """
        error = self.assertRaises(
            TypeError, type, "NewCommand", (amp.Command, ),
            {"commandName": u"FOO"})
        self.assertRegex(
            str(error), "^Command names must be byte strings, got: u?'FOO'$")


    def test_commandArgumentsMustBeNamedWithByteStrings(self):
        """
        A L{Command} subclass's C{arguments} must have byte string names.
        """
        error = self.assertRaises(
            TypeError, type, "NewCommand", (amp.Command, ),
            {"arguments": [(u"foo", None)]})
        self.assertRegex(
            str(error), "^Argument names must be byte strings, got: u?'foo'$")


    def test_commandResponseMustBeNamedWithByteStrings(self):
        """
        A L{Command} subclass's C{response} must have byte string names.
        """
        error = self.assertRaises(
            TypeError, type, "NewCommand", (amp.Command, ),
            {"response": [(u"foo", None)]})
        self.assertRegex(
            str(error), "^Response names must be byte strings, got: u?'foo'$")


    def test_commandErrorsIsConvertedToDict(self):
        """
        A L{Command} subclass's C{errors} is coerced into a C{dict}.
        """
        class NewCommand(amp.Command):
            errors = [(ZeroDivisionError, b"ZDE")]

        self.assertEqual(
            {ZeroDivisionError: b"ZDE"},
            NewCommand.errors)


    def test_commandErrorsMustUseBytesForOnWireRepresentation(self):
        """
        A L{Command} subclass's C{errors} must map exceptions to byte strings.
        """
        error = self.assertRaises(
            TypeError, type, "NewCommand", (amp.Command, ),
            {"errors": [(ZeroDivisionError, u"foo")]})
        self.assertRegex(
            str(error), "^Error names must be byte strings, got: u?'foo'$")


    def test_commandFatalErrorsIsConvertedToDict(self):
        """
        A L{Command} subclass's C{fatalErrors} is coerced into a C{dict}.
        """
        class NewCommand(amp.Command):
            fatalErrors = [(ZeroDivisionError, b"ZDE")]

        self.assertEqual(
            {ZeroDivisionError: b"ZDE"},
            NewCommand.fatalErrors)


    def test_commandFatalErrorsMustUseBytesForOnWireRepresentation(self):
        """
        A L{Command} subclass's C{fatalErrors} must map exceptions to byte
        strings.
        """
        error = self.assertRaises(
            TypeError, type, "NewCommand", (amp.Command, ),
            {"fatalErrors": [(ZeroDivisionError, u"foo")]})
        self.assertRegex(
            str(error), "^Fatal error names must be byte strings, "
            "got: u?'foo'$")



class ListOfTestsMixin:
    """
    Base class for testing L{ListOf}, a parameterized zero-or-more argument
    type.

    @ivar elementType: Subclasses should set this to an L{Argument}
        instance.  The tests will make a L{ListOf} using this.

    @ivar strings: Subclasses should set this to a dictionary mapping some
        number of keys -- as BYTE strings -- to the correct serialized form
        for some example values. These should agree with what L{elementType}
        produces/accepts.

    @ivar objects: Subclasses should set this to a dictionary with the same
        keys as C{strings} -- as NATIVE strings -- and with values which are
        the lists which should serialize to the values in the C{strings}
        dictionary.
    """
    def test_toBox(self):
        """
        L{ListOf.toBox} extracts the list of objects from the C{objects}
        dictionary passed to it, using the C{name} key also passed to it,
        serializes each of the elements in that list using the L{Argument}
        instance previously passed to its initializer, combines the serialized
        results, and inserts the result into the C{strings} dictionary using
        the same C{name} key.
        """
        stringList = amp.ListOf(self.elementType)
        strings = amp.AmpBox()
        for key in self.objects:
            stringList.toBox(
                key.encode("ascii"), strings, self.objects.copy(), None)
        self.assertEqual(strings, self.strings)


    def test_fromBox(self):
        """
        L{ListOf.fromBox} reverses the operation performed by L{ListOf.toBox}.
        """
        stringList = amp.ListOf(self.elementType)
        objects = {}
        for key in self.strings:
            stringList.fromBox(key, self.strings.copy(), objects, None)
        self.assertEqual(objects, self.objects)



class ListOfStringsTests(unittest.TestCase, ListOfTestsMixin):
    """
    Tests for L{ListOf} combined with L{amp.String}.
    """
    elementType = amp.String()

    strings = {
        b"empty": b"",
        b"single": b"\x00\x03foo",
        b"multiple": b"\x00\x03bar\x00\x03baz\x00\x04quux"}

    objects = {
        "empty": [],
        "single": [b"foo"],
        "multiple": [b"bar", b"baz", b"quux"]}


class ListOfIntegersTests(unittest.TestCase, ListOfTestsMixin):
    """
    Tests for L{ListOf} combined with L{amp.Integer}.
    """
    elementType = amp.Integer()

    huge = (
        9999999999999999999999999999999999999999999999999999999999 *
        9999999999999999999999999999999999999999999999999999999999)

    strings = {
        b"empty": b"",
        b"single": b"\x00\x0210",
        b"multiple": b"\x00\x011\x00\x0220\x00\x03500",
        b"huge": b"\x00\x74" + intToBytes(huge),
        b"negative": b"\x00\x02-1"}

    objects = {
        "empty": [],
        "single": [10],
        "multiple": [1, 20, 500],
        "huge": [huge],
        "negative": [-1]}



class ListOfUnicodeTests(unittest.TestCase, ListOfTestsMixin):
    """
    Tests for L{ListOf} combined with L{amp.Unicode}.
    """
    elementType = amp.Unicode()

    strings = {
        b"empty": b"",
        b"single": b"\x00\x03foo",
        b"multiple": b"\x00\x03\xe2\x98\x83\x00\x05Hello\x00\x05world"}

    objects = {
        "empty": [],
        "single": [u"foo"],
        "multiple": [u"\N{SNOWMAN}", u"Hello", u"world"]}



class ListOfDecimalTests(unittest.TestCase, ListOfTestsMixin):
    """
    Tests for L{ListOf} combined with L{amp.Decimal}.
    """
    elementType = amp.Decimal()

    strings = {
        b"empty": b"",
        b"single": b"\x00\x031.1",
        b"extreme": b"\x00\x08Infinity\x00\x09-Infinity",
        b"scientist": b"\x00\x083.141E+5\x00\x0a0.00003141\x00\x083.141E-7"
                      b"\x00\x09-3.141E+5\x00\x0b-0.00003141\x00\x09-3.141E-7",
        b"engineer": (
            b"\x00\x04" +
            decimal.Decimal("0e6").to_eng_string().encode("ascii") +
            b"\x00\x06" +
            decimal.Decimal("1.5E-9").to_eng_string().encode("ascii")),
    }

    objects = {
        "empty": [],
        "single": [decimal.Decimal("1.1")],
        "extreme": [
            decimal.Decimal("Infinity"),
            decimal.Decimal("-Infinity"),
        ],
        # exarkun objected to AMP supporting engineering notation because
        # it was redundant, until we realised that 1E6 has less precision
        # than 1000000 and is represented differently.  But they compare
        # and even hash equally.  There were tears.
        "scientist": [
            decimal.Decimal("3.141E5"),
            decimal.Decimal("3.141e-5"),
            decimal.Decimal("3.141E-7"),
            decimal.Decimal("-3.141e5"),
            decimal.Decimal("-3.141E-5"),
            decimal.Decimal("-3.141e-7"),
        ],
        "engineer": [
            decimal.Decimal("0e6"),
            decimal.Decimal("1.5E-9"),
        ],
     }



class ListOfDecimalNanTests(unittest.TestCase, ListOfTestsMixin):
    """
    Tests for L{ListOf} combined with L{amp.Decimal} for not-a-number values.
    """
    elementType = amp.Decimal()

    strings = {
        b"nan": b"\x00\x03NaN\x00\x04-NaN\x00\x04sNaN\x00\x05-sNaN",
    }

    objects = {
        "nan": [
            decimal.Decimal("NaN"),
            decimal.Decimal("-NaN"),
            decimal.Decimal("sNaN"),
            decimal.Decimal("-sNaN"),
        ]
    }

    def test_fromBox(self):
        """
        L{ListOf.fromBox} reverses the operation performed by L{ListOf.toBox}.
        """
        # Helpers.  Decimal.is_{qnan,snan,signed}() are new in 2.6 (or 2.5.2,
        # but who's counting).
        def is_qnan(decimal):
            return 'NaN' in str(decimal) and 'sNaN' not in str(decimal)

        def is_snan(decimal):
            return 'sNaN' in str(decimal)

        def is_signed(decimal):
            return '-' in str(decimal)

        # NaN values have unusual equality semantics, so this method is
        # overridden to compare the resulting objects in a way which works with
        # NaNs.
        stringList = amp.ListOf(self.elementType)
        objects = {}
        for key in self.strings:
            stringList.fromBox(key, self.strings.copy(), objects, None)
        n = objects["nan"]
        self.assertTrue(is_qnan(n[0]) and not is_signed(n[0]))
        self.assertTrue(is_qnan(n[1]) and is_signed(n[1]))
        self.assertTrue(is_snan(n[2]) and not is_signed(n[2]))
        self.assertTrue(is_snan(n[3]) and is_signed(n[3]))



class DecimalTests(unittest.TestCase):
    """
    Tests for L{amp.Decimal}.
    """
    def test_nonDecimal(self):
        """
        L{amp.Decimal.toString} raises L{ValueError} if passed an object which
        is not an instance of C{decimal.Decimal}.
        """
        argument = amp.Decimal()
        self.assertRaises(ValueError, argument.toString, "1.234")
        self.assertRaises(ValueError, argument.toString, 1.234)
        self.assertRaises(ValueError, argument.toString, 1234)



class FloatTests(unittest.TestCase):
    """
    Tests for L{amp.Float}.
    """
    def test_nonFloat(self):
        """
        L{amp.Float.toString} raises L{ValueError} if passed an object which
        is not a L{float}.
        """
        argument = amp.Float()
        self.assertRaises(ValueError, argument.toString, u"1.234")
        self.assertRaises(ValueError, argument.toString, b"1.234")
        self.assertRaises(ValueError, argument.toString, 1234)


    def test_float(self):
        """
        L{amp.Float.toString} returns a bytestring when it is given a L{float}.
        """
        argument = amp.Float()
        self.assertEqual(argument.toString(1.234), b"1.234")



class ListOfDateTimeTests(unittest.TestCase, ListOfTestsMixin):
    """
    Tests for L{ListOf} combined with L{amp.DateTime}.
    """
    elementType = amp.DateTime()

    strings = {
        b"christmas": b"\x00\x202010-12-25T00:00:00.000000-00:00"
                      b"\x00\x202010-12-25T00:00:00.000000-00:00",
        b"christmas in eu": b"\x00\x202010-12-25T00:00:00.000000+01:00",
        b"christmas in iran": b"\x00\x202010-12-25T00:00:00.000000+03:30",
        b"christmas in nyc": b"\x00\x202010-12-25T00:00:00.000000-05:00",
        b"previous tests": b"\x00\x202010-12-25T00:00:00.000000+03:19"
                           b"\x00\x202010-12-25T00:00:00.000000-06:59",
    }

    objects = {
        "christmas": [
            datetime.datetime(2010, 12, 25, 0, 0, 0, tzinfo=amp.utc),
            datetime.datetime(2010, 12, 25, 0, 0, 0, tzinfo=tz('+', 0, 0)),
        ],
        "christmas in eu": [
            datetime.datetime(2010, 12, 25, 0, 0, 0, tzinfo=tz('+', 1, 0)),
        ],
        "christmas in iran": [
            datetime.datetime(2010, 12, 25, 0, 0, 0, tzinfo=tz('+', 3, 30)),
        ],
        "christmas in nyc": [
            datetime.datetime(2010, 12, 25, 0, 0, 0, tzinfo=tz('-', 5, 0)),
        ],
        "previous tests": [
            datetime.datetime(2010, 12, 25, 0, 0, 0, tzinfo=tz('+', 3, 19)),
            datetime.datetime(2010, 12, 25, 0, 0, 0, tzinfo=tz('-', 6, 59)),
        ],
    }



class ListOfOptionalTests(unittest.TestCase):
    """
    Tests to ensure L{ListOf} AMP arguments can be omitted from AMP commands
    via the 'optional' flag.
    """
    def test_requiredArgumentWithNoneValueRaisesTypeError(self):
        """
        L{ListOf.toBox} raises C{TypeError} when passed a value of L{None}
        for the argument.
        """
        stringList = amp.ListOf(amp.Integer())
        self.assertRaises(
            TypeError, stringList.toBox, b'omitted', amp.AmpBox(),
            {'omitted': None}, None)


    def test_optionalArgumentWithNoneValueOmitted(self):
        """
        L{ListOf.toBox} silently omits serializing any argument with a
        value of L{None} that is designated as optional for the protocol.
        """
        stringList = amp.ListOf(amp.Integer(), optional=True)
        strings = amp.AmpBox()
        stringList.toBox(b'omitted', strings, {b'omitted': None}, None)
        self.assertEqual(strings, {})


    def test_requiredArgumentWithKeyMissingRaisesKeyError(self):
        """
        L{ListOf.toBox} raises C{KeyError} if the argument's key is not
        present in the objects dictionary.
        """
        stringList = amp.ListOf(amp.Integer())
        self.assertRaises(
            KeyError, stringList.toBox, b'ommited', amp.AmpBox(),
            {'someOtherKey': 0}, None)


    def test_optionalArgumentWithKeyMissingOmitted(self):
        """
        L{ListOf.toBox} silently omits serializing any argument designated
        as optional whose key is not present in the objects dictionary.
        """
        stringList = amp.ListOf(amp.Integer(), optional=True)
        stringList.toBox(b'ommited', amp.AmpBox(), {b'someOtherKey': 0}, None)


    def test_omittedOptionalArgumentDeserializesAsNone(self):
        """
        L{ListOf.fromBox} correctly reverses the operation performed by
        L{ListOf.toBox} for optional arguments.
        """
        stringList = amp.ListOf(amp.Integer(), optional=True)
        objects = {}
        stringList.fromBox(b'omitted', {}, objects, None)
        self.assertEqual(objects, {'omitted': None})



@implementer(interfaces.IUNIXTransport)
class UNIXStringTransport(object):
    """
    An in-memory implementation of L{interfaces.IUNIXTransport} which collects
    all data given to it for later inspection.

    @ivar _queue: A C{list} of the data which has been given to this transport,
        eg via C{write} or C{sendFileDescriptor}.  Elements are two-tuples of a
        string (identifying the destination of the data) and the data itself.
    """

    def __init__(self, descriptorFuzz):
        """
        @param descriptorFuzz: An offset to apply to descriptors.
        @type descriptorFuzz: C{int}
        """
        self._fuzz = descriptorFuzz
        self._queue = []


    def sendFileDescriptor(self, descriptor):
        self._queue.append((
                'fileDescriptorReceived', descriptor + self._fuzz))


    def write(self, data):
        self._queue.append(('dataReceived', data))


    def writeSequence(self, seq):
        for data in seq:
            self.write(data)


    def loseConnection(self):
        self._queue.append(('connectionLost', Failure(error.ConnectionLost())))


    def getHost(self):
        return address.UNIXAddress('/tmp/some-path')


    def getPeer(self):
        return address.UNIXAddress('/tmp/another-path')

# Minimal evidence that we got the signatures right
verifyClass(interfaces.ITransport, UNIXStringTransport)
verifyClass(interfaces.IUNIXTransport, UNIXStringTransport)


class DescriptorTests(unittest.TestCase):
    """
    Tests for L{amp.Descriptor}, an argument type for passing a file descriptor
    over an AMP connection over a UNIX domain socket.
    """
    def setUp(self):
        self.fuzz = 3
        self.transport = UNIXStringTransport(descriptorFuzz=self.fuzz)
        self.protocol = amp.BinaryBoxProtocol(
            amp.BoxDispatcher(amp.CommandLocator()))
        self.protocol.makeConnection(self.transport)


    def test_fromStringProto(self):
        """
        L{Descriptor.fromStringProto} constructs a file descriptor value by
        extracting a previously received file descriptor corresponding to the
        wire value of the argument from the L{_DescriptorExchanger} state of the
        protocol passed to it.

        This is a whitebox test which involves direct L{_DescriptorExchanger}
        state inspection.
        """
        argument = amp.Descriptor()
        self.protocol.fileDescriptorReceived(5)
        self.protocol.fileDescriptorReceived(3)
        self.protocol.fileDescriptorReceived(1)
        self.assertEqual(
            5, argument.fromStringProto("0", self.protocol))
        self.assertEqual(
            3, argument.fromStringProto("1", self.protocol))
        self.assertEqual(
            1, argument.fromStringProto("2", self.protocol))
        self.assertEqual({}, self.protocol._descriptors)


    def test_toStringProto(self):
        """
        To send a file descriptor, L{Descriptor.toStringProto} uses the
        L{IUNIXTransport.sendFileDescriptor} implementation of the transport of
        the protocol passed to it to copy the file descriptor.  Each subsequent
        descriptor sent over a particular AMP connection is assigned the next
        integer value, starting from 0.  The base ten string representation of
        this value is the byte encoding of the argument.

        This is a whitebox test which involves direct L{_DescriptorExchanger}
        state inspection and mutation.
        """
        argument = amp.Descriptor()
        self.assertEqual(b"0", argument.toStringProto(2, self.protocol))
        self.assertEqual(
            ("fileDescriptorReceived", 2 + self.fuzz), self.transport._queue.pop(0))
        self.assertEqual(b"1", argument.toStringProto(4, self.protocol))
        self.assertEqual(
            ("fileDescriptorReceived", 4 + self.fuzz), self.transport._queue.pop(0))
        self.assertEqual(b"2", argument.toStringProto(6, self.protocol))
        self.assertEqual(
            ("fileDescriptorReceived", 6 + self.fuzz), self.transport._queue.pop(0))
        self.assertEqual({}, self.protocol._descriptors)


    def test_roundTrip(self):
        """
        L{amp.Descriptor.fromBox} can interpret an L{amp.AmpBox} constructed by
        L{amp.Descriptor.toBox} to reconstruct a file descriptor value.
        """
        name = "alpha"
        nameAsBytes = name.encode("ascii")
        strings = {}
        descriptor = 17
        sendObjects = {name: descriptor}

        argument = amp.Descriptor()
        argument.toBox(nameAsBytes, strings, sendObjects.copy(), self.protocol)

        receiver = amp.BinaryBoxProtocol(
            amp.BoxDispatcher(amp.CommandLocator()))
        for event in self.transport._queue:
            getattr(receiver, event[0])(*event[1:])

        receiveObjects = {}
        argument.fromBox(
            nameAsBytes, strings.copy(), receiveObjects, receiver)

        # Make sure we got the descriptor.  Adjust by fuzz to be more convincing
        # of having gone through L{IUNIXTransport.sendFileDescriptor}, not just
        # converted to a string and then parsed back into an integer.
        self.assertEqual(descriptor + self.fuzz, receiveObjects[name])



class DateTimeTests(unittest.TestCase):
    """
    Tests for L{amp.DateTime}, L{amp._FixedOffsetTZInfo}, and L{amp.utc}.
    """
    string = b'9876-01-23T12:34:56.054321-01:23'
    tzinfo = tz('-', 1, 23)
    object = datetime.datetime(9876, 1, 23, 12, 34, 56, 54321, tzinfo)

    def test_invalidString(self):
        """
        L{amp.DateTime.fromString} raises L{ValueError} when passed a string
        which does not represent a timestamp in the proper format.
        """
        d = amp.DateTime()
        self.assertRaises(ValueError, d.fromString, 'abc')


    def test_invalidDatetime(self):
        """
        L{amp.DateTime.toString} raises L{ValueError} when passed a naive
        datetime (a datetime with no timezone information).
        """
        d = amp.DateTime()
        self.assertRaises(ValueError, d.toString,
            datetime.datetime(2010, 12, 25, 0, 0, 0))


    def test_fromString(self):
        """
        L{amp.DateTime.fromString} returns a C{datetime.datetime} with all of
        its fields populated from the string passed to it.
        """
        argument = amp.DateTime()
        value = argument.fromString(self.string)
        self.assertEqual(value, self.object)


    def test_toString(self):
        """
        L{amp.DateTime.toString} returns a C{str} in the wire format including
        all of the information from the C{datetime.datetime} passed into it,
        including the timezone offset.
        """
        argument = amp.DateTime()
        value = argument.toString(self.object)
        self.assertEqual(value, self.string)



class UTCTests(unittest.TestCase):
    """
    Tests for L{amp.utc}.
    """

    def test_tzname(self):
        """
        L{amp.utc.tzname} returns C{"+00:00"}.
        """
        self.assertEqual(amp.utc.tzname(None), '+00:00')


    def test_dst(self):
        """
        L{amp.utc.dst} returns a zero timedelta.
        """
        self.assertEqual(amp.utc.dst(None), datetime.timedelta(0))


    def test_utcoffset(self):
        """
        L{amp.utc.utcoffset} returns a zero timedelta.
        """
        self.assertEqual(amp.utc.utcoffset(None), datetime.timedelta(0))


    def test_badSign(self):
        """
        L{amp._FixedOffsetTZInfo.fromSignHoursMinutes} raises L{ValueError} if
        passed an offset sign other than C{'+'} or C{'-'}.
        """
        self.assertRaises(ValueError, tz, '?', 0, 0)



class RemoteAmpErrorTests(unittest.TestCase):
    """
    Tests for L{amp.RemoteAmpError}.
    """

    def test_stringMessage(self):
        """
        L{amp.RemoteAmpError} renders the given C{errorCode} (C{bytes}) and
        C{description} into a native string.
        """
        error = amp.RemoteAmpError(b"BROKEN", "Something has broken")
        self.assertEqual("Code<BROKEN>: Something has broken", str(error))


    def test_stringMessageReplacesNonAsciiText(self):
        """
        When C{errorCode} contains non-ASCII characters, L{amp.RemoteAmpError}
        renders then as backslash-escape sequences.
        """
        error = amp.RemoteAmpError(b"BROKEN-\xff", "Something has broken")
        self.assertEqual("Code<BROKEN-\\xff>: Something has broken", str(error))


    def test_stringMessageWithLocalFailure(self):
        """
        L{amp.RemoteAmpError} renders local errors with a "(local)" marker and
        a brief traceback.
        """
        failure = Failure(Exception("Something came loose"))
        error = amp.RemoteAmpError(
            b"BROKEN", "Something has broken", local=failure)
        self.assertRegex(
            str(error), (
                "^Code<BROKEN> [(]local[)]: Something has broken\n"
                "Traceback [(]failure with no frames[)]: "
                "<.+Exception.>: Something came loose\n"
            ))



if not interfaces.IReactorSSL.providedBy(reactor):
    skipMsg = 'This test case requires SSL support in the reactor'
    TLSTests.skip = skipMsg
    LiveFireTLSTests.skip = skipMsg
    PlainVanillaLiveFireTests.skip = skipMsg
    WithServerTLSVerificationTests.skip = skipMsg

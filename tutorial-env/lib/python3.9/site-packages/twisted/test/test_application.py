# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.application} and its interaction with
L{twisted.persisted.sob}.
"""


import copy
import os
import pickle
from io import StringIO

try:
    import asyncio
except ImportError:
    asyncio = None  # type: ignore[assignment]

from unittest import skipIf

from twisted.application import app, internet, reactors, service
from twisted.application.internet import backoffPolicy
from twisted.internet import defer, interfaces, protocol, reactor
from twisted.persisted import sob
from twisted.plugins import twisted_reactors
from twisted.protocols import basic, wire
from twisted.python import usage
from twisted.python.runtime import platformType
from twisted.python.test.modules_helpers import TwistedModulesMixin
from twisted.test.proto_helpers import MemoryReactor
from twisted.trial.unittest import SkipTest, TestCase


class Dummy:
    processName = None


class ServiceTests(TestCase):
    def testName(self):
        s = service.Service()
        s.setName("hello")
        self.assertEqual(s.name, "hello")

    def testParent(self):
        s = service.Service()
        p = service.MultiService()
        s.setServiceParent(p)
        self.assertEqual(list(p), [s])
        self.assertEqual(s.parent, p)

    def testApplicationAsParent(self):
        s = service.Service()
        p = service.Application("")
        s.setServiceParent(p)
        self.assertEqual(list(service.IServiceCollection(p)), [s])
        self.assertEqual(s.parent, service.IServiceCollection(p))

    def testNamedChild(self):
        s = service.Service()
        p = service.MultiService()
        s.setName("hello")
        s.setServiceParent(p)
        self.assertEqual(list(p), [s])
        self.assertEqual(s.parent, p)
        self.assertEqual(p.getServiceNamed("hello"), s)

    def testDoublyNamedChild(self):
        s = service.Service()
        p = service.MultiService()
        s.setName("hello")
        s.setServiceParent(p)
        self.assertRaises(RuntimeError, s.setName, "lala")

    def testDuplicateNamedChild(self):
        s = service.Service()
        p = service.MultiService()
        s.setName("hello")
        s.setServiceParent(p)
        s = service.Service()
        s.setName("hello")
        self.assertRaises(RuntimeError, s.setServiceParent, p)

    def testDisowning(self):
        s = service.Service()
        p = service.MultiService()
        s.setServiceParent(p)
        self.assertEqual(list(p), [s])
        self.assertEqual(s.parent, p)
        s.disownServiceParent()
        self.assertEqual(list(p), [])
        self.assertIsNone(s.parent)

    def testRunning(self):
        s = service.Service()
        self.assertFalse(s.running)
        s.startService()
        self.assertTrue(s.running)
        s.stopService()
        self.assertFalse(s.running)

    def testRunningChildren1(self):
        s = service.Service()
        p = service.MultiService()
        s.setServiceParent(p)
        self.assertFalse(s.running)
        self.assertFalse(p.running)
        p.startService()
        self.assertTrue(s.running)
        self.assertTrue(p.running)
        p.stopService()
        self.assertFalse(s.running)
        self.assertFalse(p.running)

    def testRunningChildren2(self):
        s = service.Service()

        def checkRunning():
            self.assertTrue(s.running)

        t = service.Service()
        t.stopService = checkRunning
        t.startService = checkRunning
        p = service.MultiService()
        s.setServiceParent(p)
        t.setServiceParent(p)
        p.startService()
        p.stopService()

    def testAddingIntoRunning(self):
        p = service.MultiService()
        p.startService()
        s = service.Service()
        self.assertFalse(s.running)
        s.setServiceParent(p)
        self.assertTrue(s.running)
        s.disownServiceParent()
        self.assertFalse(s.running)

    def testPrivileged(self):
        s = service.Service()

        def pss():
            s.privilegedStarted = 1

        s.privilegedStartService = pss
        s1 = service.Service()
        p = service.MultiService()
        s.setServiceParent(p)
        s1.setServiceParent(p)
        p.privilegedStartService()
        self.assertTrue(s.privilegedStarted)

    def testCopying(self):
        s = service.Service()
        s.startService()
        s1 = copy.copy(s)
        self.assertFalse(s1.running)
        self.assertTrue(s.running)


if hasattr(os, "getuid"):
    curuid = os.getuid()
    curgid = os.getgid()
else:
    curuid = curgid = 0


class ProcessTests(TestCase):
    def testID(self):
        p = service.Process(5, 6)
        self.assertEqual(p.uid, 5)
        self.assertEqual(p.gid, 6)

    def testDefaults(self):
        p = service.Process(5)
        self.assertEqual(p.uid, 5)
        self.assertIsNone(p.gid)
        p = service.Process(gid=5)
        self.assertIsNone(p.uid)
        self.assertEqual(p.gid, 5)
        p = service.Process()
        self.assertIsNone(p.uid)
        self.assertIsNone(p.gid)

    def testProcessName(self):
        p = service.Process()
        self.assertIsNone(p.processName)
        p.processName = "hello"
        self.assertEqual(p.processName, "hello")


class InterfacesTests(TestCase):
    def testService(self):
        self.assertTrue(service.IService.providedBy(service.Service()))

    def testMultiService(self):
        self.assertTrue(service.IService.providedBy(service.MultiService()))
        self.assertTrue(service.IServiceCollection.providedBy(service.MultiService()))

    def testProcess(self):
        self.assertTrue(service.IProcess.providedBy(service.Process()))


class ApplicationTests(TestCase):
    def testConstructor(self):
        service.Application("hello")
        service.Application("hello", 5)
        service.Application("hello", 5, 6)

    def testProcessComponent(self):
        a = service.Application("hello")
        self.assertIsNone(service.IProcess(a).uid)
        self.assertIsNone(service.IProcess(a).gid)
        a = service.Application("hello", 5)
        self.assertEqual(service.IProcess(a).uid, 5)
        self.assertIsNone(service.IProcess(a).gid)
        a = service.Application("hello", 5, 6)
        self.assertEqual(service.IProcess(a).uid, 5)
        self.assertEqual(service.IProcess(a).gid, 6)

    def testServiceComponent(self):
        a = service.Application("hello")
        self.assertIs(service.IService(a), service.IServiceCollection(a))
        self.assertEqual(service.IService(a).name, "hello")
        self.assertIsNone(service.IService(a).parent)

    def testPersistableComponent(self):
        a = service.Application("hello")
        p = sob.IPersistable(a)
        self.assertEqual(p.style, "pickle")
        self.assertEqual(p.name, "hello")
        self.assertIs(p.original, a)


class LoadingTests(TestCase):
    def test_simpleStoreAndLoad(self):
        a = service.Application("hello")
        p = sob.IPersistable(a)
        for style in "source pickle".split():
            p.setStyle(style)
            p.save()
            a1 = service.loadApplication("hello.ta" + style[0], style)
            self.assertEqual(service.IService(a1).name, "hello")
        with open("hello.tac", "w") as f:
            f.writelines(
                [
                    "from twisted.application import service\n",
                    "application = service.Application('hello')\n",
                ]
            )
        a1 = service.loadApplication("hello.tac", "python")
        self.assertEqual(service.IService(a1).name, "hello")


class AppSupportTests(TestCase):
    def testPassphrase(self):
        self.assertIsNone(app.getPassphrase(0))

    def testLoadApplication(self):
        """
        Test loading an application file in different dump format.
        """
        a = service.Application("hello")
        baseconfig = {"file": None, "source": None, "python": None}
        for style in "source pickle".split():
            config = baseconfig.copy()
            config[{"pickle": "file"}.get(style, style)] = "helloapplication"
            sob.IPersistable(a).setStyle(style)
            sob.IPersistable(a).save(filename="helloapplication")
            a1 = app.getApplication(config, None)
            self.assertEqual(service.IService(a1).name, "hello")
        config = baseconfig.copy()
        config["python"] = "helloapplication"
        with open("helloapplication", "w") as f:
            f.writelines(
                [
                    "from twisted.application import service\n",
                    "application = service.Application('hello')\n",
                ]
            )
        a1 = app.getApplication(config, None)
        self.assertEqual(service.IService(a1).name, "hello")

    def test_convertStyle(self):
        appl = service.Application("lala")
        for instyle in "source pickle".split():
            for outstyle in "source pickle".split():
                sob.IPersistable(appl).setStyle(instyle)
                sob.IPersistable(appl).save(filename="converttest")
                app.convertStyle(
                    "converttest", instyle, None, "converttest.out", outstyle, 0
                )
                appl2 = service.loadApplication("converttest.out", outstyle)
                self.assertEqual(service.IService(appl2).name, "lala")

    def test_startApplication(self):
        appl = service.Application("lala")
        app.startApplication(appl, 0)
        self.assertTrue(service.IService(appl).running)


class Foo(basic.LineReceiver):
    def connectionMade(self):
        self.transport.write(b"lalala\r\n")

    def lineReceived(self, line):
        self.factory.line = line
        self.transport.loseConnection()

    def connectionLost(self, reason):
        self.factory.d.callback(self.factory.line)


class DummyApp:
    processName = None

    def addService(self, service):
        self.services[service.name] = service

    def removeService(self, service):
        del self.services[service.name]


class TimerTarget:
    def __init__(self):
        self.l = []

    def append(self, what):
        self.l.append(what)


class TestEcho(wire.Echo):
    def connectionLost(self, reason):
        self.d.callback(True)


class InternetTests(TestCase):
    def testTCP(self):
        s = service.MultiService()
        s.startService()
        factory = protocol.ServerFactory()
        factory.protocol = TestEcho
        TestEcho.d = defer.Deferred()
        t = internet.TCPServer(0, factory)
        t.setServiceParent(s)
        num = t._port.getHost().port
        factory = protocol.ClientFactory()
        factory.d = defer.Deferred()
        factory.protocol = Foo
        factory.line = None
        internet.TCPClient("127.0.0.1", num, factory).setServiceParent(s)
        factory.d.addCallback(self.assertEqual, b"lalala")
        factory.d.addCallback(lambda x: s.stopService())
        factory.d.addCallback(lambda x: TestEcho.d)
        return factory.d

    def test_UDP(self):
        """
        Test L{internet.UDPServer} with a random port: starting the service
        should give it valid port, and stopService should free it so that we
        can start a server on the same port again.
        """
        if not interfaces.IReactorUDP(reactor, None):
            raise SkipTest("This reactor does not support UDP sockets")
        p = protocol.DatagramProtocol()
        t = internet.UDPServer(0, p)
        t.startService()
        num = t._port.getHost().port
        self.assertNotEqual(num, 0)

        def onStop(ignored):
            t = internet.UDPServer(num, p)
            t.startService()
            return t.stopService()

        return defer.maybeDeferred(t.stopService).addCallback(onStop)

    def testPrivileged(self):
        factory = protocol.ServerFactory()
        factory.protocol = TestEcho
        TestEcho.d = defer.Deferred()
        t = internet.TCPServer(0, factory)
        t.privileged = 1
        t.privilegedStartService()
        num = t._port.getHost().port
        factory = protocol.ClientFactory()
        factory.d = defer.Deferred()
        factory.protocol = Foo
        factory.line = None
        c = internet.TCPClient("127.0.0.1", num, factory)
        c.startService()
        factory.d.addCallback(self.assertEqual, b"lalala")
        factory.d.addCallback(lambda x: c.stopService())
        factory.d.addCallback(lambda x: t.stopService())
        factory.d.addCallback(lambda x: TestEcho.d)
        return factory.d

    def testConnectionGettingRefused(self):
        factory = protocol.ServerFactory()
        factory.protocol = wire.Echo
        t = internet.TCPServer(0, factory)
        t.startService()
        num = t._port.getHost().port
        t.stopService()
        d = defer.Deferred()
        factory = protocol.ClientFactory()
        factory.clientConnectionFailed = lambda *args: d.callback(None)
        c = internet.TCPClient("127.0.0.1", num, factory)
        c.startService()
        return d

    @skipIf(
        not interfaces.IReactorUNIX(reactor, None),
        "This reactor does not support UNIX domain sockets",
    )
    def testUNIX(self):
        # FIXME: This test is far too dense.  It needs comments.
        #  -- spiv, 2004-11-07
        s = service.MultiService()
        s.startService()
        factory = protocol.ServerFactory()
        factory.protocol = TestEcho
        TestEcho.d = defer.Deferred()
        t = internet.UNIXServer("echo.skt", factory)
        t.setServiceParent(s)
        factory = protocol.ClientFactory()
        factory.protocol = Foo
        factory.d = defer.Deferred()
        factory.line = None
        internet.UNIXClient("echo.skt", factory).setServiceParent(s)
        factory.d.addCallback(self.assertEqual, b"lalala")
        factory.d.addCallback(lambda x: s.stopService())
        factory.d.addCallback(lambda x: TestEcho.d)
        factory.d.addCallback(self._cbTestUnix, factory, s)
        return factory.d

    def _cbTestUnix(self, ignored, factory, s):
        TestEcho.d = defer.Deferred()
        factory.line = None
        factory.d = defer.Deferred()
        s.startService()
        factory.d.addCallback(self.assertEqual, b"lalala")
        factory.d.addCallback(lambda x: s.stopService())
        factory.d.addCallback(lambda x: TestEcho.d)
        return factory.d

    @skipIf(
        not interfaces.IReactorUNIX(reactor, None),
        "This reactor does not support UNIX domain sockets",
    )
    def testVolatile(self):
        factory = protocol.ServerFactory()
        factory.protocol = wire.Echo
        t = internet.UNIXServer("echo.skt", factory)
        t.startService()
        self.failIfIdentical(t._port, None)
        t1 = copy.copy(t)
        self.assertIsNone(t1._port)
        t.stopService()
        self.assertIsNone(t._port)
        self.assertFalse(t.running)

        factory = protocol.ClientFactory()
        factory.protocol = wire.Echo
        t = internet.UNIXClient("echo.skt", factory)
        t.startService()
        self.failIfIdentical(t._connection, None)
        t1 = copy.copy(t)
        self.assertIsNone(t1._connection)
        t.stopService()
        self.assertIsNone(t._connection)
        self.assertFalse(t.running)

    @skipIf(
        not interfaces.IReactorUNIX(reactor, None),
        "This reactor does not support UNIX domain sockets",
    )
    def testStoppingServer(self):
        factory = protocol.ServerFactory()
        factory.protocol = wire.Echo
        t = internet.UNIXServer("echo.skt", factory)
        t.startService()
        t.stopService()
        self.assertFalse(t.running)
        factory = protocol.ClientFactory()
        d = defer.Deferred()
        factory.clientConnectionFailed = lambda *args: d.callback(None)
        reactor.connectUNIX("echo.skt", factory)
        return d

    def testPickledTimer(self):
        target = TimerTarget()
        t0 = internet.TimerService(1, target.append, "hello")
        t0.startService()
        s = pickle.dumps(t0)
        t0.stopService()

        t = pickle.loads(s)
        self.assertFalse(t.running)

    def testBrokenTimer(self):
        d = defer.Deferred()
        t = internet.TimerService(1, lambda: 1 // 0)
        oldFailed = t._failed

        def _failed(why):
            oldFailed(why)
            d.callback(None)

        t._failed = _failed
        t.startService()
        d.addCallback(lambda x: t.stopService)
        d.addCallback(
            lambda x: self.assertEqual(
                [ZeroDivisionError],
                [o.value.__class__ for o in self.flushLoggedErrors(ZeroDivisionError)],
            )
        )
        return d

    def test_everythingThere(self):
        """
        L{twisted.application.internet} dynamically defines a set of
        L{service.Service} subclasses that in general have corresponding
        reactor.listenXXX or reactor.connectXXX calls.
        """
        trans = ["TCP", "UNIX", "SSL", "UDP", "UNIXDatagram", "Multicast"]
        for tran in trans[:]:
            if not getattr(interfaces, "IReactor" + tran)(reactor, None):
                trans.remove(tran)
        for tran in trans:
            for side in ["Server", "Client"]:
                if tran == "Multicast" and side == "Client":
                    continue
                if tran == "UDP" and side == "Client":
                    continue
                self.assertTrue(hasattr(internet, tran + side))
                method = getattr(internet, tran + side).method
                prefix = {"Server": "listen", "Client": "connect"}[side]
                self.assertTrue(
                    hasattr(reactor, prefix + method)
                    or (prefix == "connect" and method == "UDP")
                )
                o = getattr(internet, tran + side)()
                self.assertEqual(service.IService(o), o)

    def test_importAll(self):
        """
        L{twisted.application.internet} dynamically defines L{service.Service}
        subclasses. This test ensures that the subclasses exposed by C{__all__}
        are valid attributes of the module.
        """
        for cls in internet.__all__:
            self.assertTrue(
                hasattr(internet, cls),
                f"{cls} not importable from twisted.application.internet",
            )

    def test_reactorParametrizationInServer(self):
        """
        L{internet._AbstractServer} supports a C{reactor} keyword argument
        that can be used to parametrize the reactor used to listen for
        connections.
        """
        reactor = MemoryReactor()

        factory = object()
        t = internet.TCPServer(1234, factory, reactor=reactor)
        t.startService()
        self.assertEqual(reactor.tcpServers.pop()[:2], (1234, factory))

    def test_reactorParametrizationInClient(self):
        """
        L{internet._AbstractClient} supports a C{reactor} keyword arguments
        that can be used to parametrize the reactor used to create new client
        connections.
        """
        reactor = MemoryReactor()

        factory = protocol.ClientFactory()
        t = internet.TCPClient("127.0.0.1", 1234, factory, reactor=reactor)
        t.startService()
        self.assertEqual(reactor.tcpClients.pop()[:3], ("127.0.0.1", 1234, factory))

    def test_reactorParametrizationInServerMultipleStart(self):
        """
        Like L{test_reactorParametrizationInServer}, but stop and restart the
        service and check that the given reactor is still used.
        """
        reactor = MemoryReactor()

        factory = protocol.Factory()
        t = internet.TCPServer(1234, factory, reactor=reactor)
        t.startService()
        self.assertEqual(reactor.tcpServers.pop()[:2], (1234, factory))
        t.stopService()
        t.startService()
        self.assertEqual(reactor.tcpServers.pop()[:2], (1234, factory))

    def test_reactorParametrizationInClientMultipleStart(self):
        """
        Like L{test_reactorParametrizationInClient}, but stop and restart the
        service and check that the given reactor is still used.
        """
        reactor = MemoryReactor()

        factory = protocol.ClientFactory()
        t = internet.TCPClient("127.0.0.1", 1234, factory, reactor=reactor)
        t.startService()
        self.assertEqual(reactor.tcpClients.pop()[:3], ("127.0.0.1", 1234, factory))
        t.stopService()
        t.startService()
        self.assertEqual(reactor.tcpClients.pop()[:3], ("127.0.0.1", 1234, factory))


class TimerBasicTests(TestCase):
    def testTimerRuns(self):
        d = defer.Deferred()
        self.t = internet.TimerService(1, d.callback, "hello")
        self.t.startService()
        d.addCallback(self.assertEqual, "hello")
        d.addCallback(lambda x: self.t.stopService())
        d.addCallback(lambda x: self.assertFalse(self.t.running))
        return d

    def tearDown(self):
        return self.t.stopService()

    def testTimerRestart(self):
        # restart the same TimerService
        d1 = defer.Deferred()
        d2 = defer.Deferred()
        work = [(d2, "bar"), (d1, "foo")]

        def trigger():
            d, arg = work.pop()
            d.callback(arg)

        self.t = internet.TimerService(1, trigger)
        self.t.startService()

        def onFirstResult(result):
            self.assertEqual(result, "foo")
            return self.t.stopService()

        def onFirstStop(ignored):
            self.assertFalse(self.t.running)
            self.t.startService()
            return d2

        def onSecondResult(result):
            self.assertEqual(result, "bar")
            self.t.stopService()

        d1.addCallback(onFirstResult)
        d1.addCallback(onFirstStop)
        d1.addCallback(onSecondResult)
        return d1

    def testTimerLoops(self):
        l = []

        def trigger(data, number, d):
            l.append(data)
            if len(l) == number:
                d.callback(l)

        d = defer.Deferred()
        self.t = internet.TimerService(0.01, trigger, "hello", 10, d)
        self.t.startService()
        d.addCallback(self.assertEqual, ["hello"] * 10)
        d.addCallback(lambda x: self.t.stopService())
        return d


class FakeReactor(reactors.Reactor):
    """
    A fake reactor with a hooked install method.
    """

    def __init__(self, install, *args, **kwargs):
        """
        @param install: any callable that will be used as install method.
        @type install: C{callable}
        """
        reactors.Reactor.__init__(self, *args, **kwargs)
        self.install = install


class PluggableReactorTests(TwistedModulesMixin, TestCase):
    """
    Tests for the reactor discovery/inspection APIs.
    """

    def setUp(self):
        """
        Override the L{reactors.getPlugins} function, normally bound to
        L{twisted.plugin.getPlugins}, in order to control which
        L{IReactorInstaller} plugins are seen as available.

        C{self.pluginResults} can be customized and will be used as the
        result of calls to C{reactors.getPlugins}.
        """
        self.pluginCalls = []
        self.pluginResults = []
        self.originalFunction = reactors.getPlugins
        reactors.getPlugins = self._getPlugins

    def tearDown(self):
        """
        Restore the original L{reactors.getPlugins}.
        """
        reactors.getPlugins = self.originalFunction

    def _getPlugins(self, interface, package=None):
        """
        Stand-in for the real getPlugins method which records its arguments
        and returns a fixed result.
        """
        self.pluginCalls.append((interface, package))
        return list(self.pluginResults)

    def test_getPluginReactorTypes(self):
        """
        Test that reactor plugins are returned from L{getReactorTypes}
        """
        name = "fakereactortest"
        package = __name__ + ".fakereactor"
        description = "description"
        self.pluginResults = [reactors.Reactor(name, package, description)]
        reactorTypes = reactors.getReactorTypes()

        self.assertEqual(self.pluginCalls, [(reactors.IReactorInstaller, None)])

        for r in reactorTypes:
            if r.shortName == name:
                self.assertEqual(r.description, description)
                break
        else:
            self.fail("Reactor plugin not present in getReactorTypes() result")

    def test_reactorInstallation(self):
        """
        Test that L{reactors.Reactor.install} loads the correct module and
        calls its install attribute.
        """
        installed = []

        def install():
            installed.append(True)

        fakeReactor = FakeReactor(install, "fakereactortest", __name__, "described")
        modules = {"fakereactortest": fakeReactor}
        self.replaceSysModules(modules)
        installer = reactors.Reactor("fakereactor", "fakereactortest", "described")
        installer.install()
        self.assertEqual(installed, [True])

    def test_installReactor(self):
        """
        Test that the L{reactors.installReactor} function correctly installs
        the specified reactor.
        """
        installed = []

        def install():
            installed.append(True)

        name = "fakereactortest"
        package = __name__
        description = "description"
        self.pluginResults = [FakeReactor(install, name, package, description)]
        reactors.installReactor(name)
        self.assertEqual(installed, [True])

    def test_installReactorReturnsReactor(self):
        """
        Test that the L{reactors.installReactor} function correctly returns
        the installed reactor.
        """
        reactor = object()

        def install():
            from twisted import internet

            self.patch(internet, "reactor", reactor)

        name = "fakereactortest"
        package = __name__
        description = "description"
        self.pluginResults = [FakeReactor(install, name, package, description)]
        installed = reactors.installReactor(name)
        self.assertIs(installed, reactor)

    def test_installReactorMultiplePlugins(self):
        """
        Test that the L{reactors.installReactor} function correctly installs
        the specified reactor when there are multiple reactor plugins.
        """
        installed = []

        def install():
            installed.append(True)

        name = "fakereactortest"
        package = __name__
        description = "description"
        fakeReactor = FakeReactor(install, name, package, description)
        otherReactor = FakeReactor(lambda: None, "otherreactor", package, description)
        self.pluginResults = [otherReactor, fakeReactor]
        reactors.installReactor(name)
        self.assertEqual(installed, [True])

    def test_installNonExistentReactor(self):
        """
        Test that L{reactors.installReactor} raises L{reactors.NoSuchReactor}
        when asked to install a reactor which it cannot find.
        """
        self.pluginResults = []
        self.assertRaises(
            reactors.NoSuchReactor, reactors.installReactor, "somereactor"
        )

    def test_installNotAvailableReactor(self):
        """
        Test that L{reactors.installReactor} raises an exception when asked to
        install a reactor which doesn't work in this environment.
        """

        def install():
            raise ImportError("Missing foo bar")

        name = "fakereactortest"
        package = __name__
        description = "description"
        self.pluginResults = [FakeReactor(install, name, package, description)]
        self.assertRaises(ImportError, reactors.installReactor, name)

    def test_reactorSelectionMixin(self):
        """
        Test that the reactor selected is installed as soon as possible, ie
        when the option is parsed.
        """
        executed = []
        INSTALL_EVENT = "reactor installed"
        SUBCOMMAND_EVENT = "subcommands loaded"

        class ReactorSelectionOptions(usage.Options, app.ReactorSelectionMixin):
            @property
            def subCommands(self):
                executed.append(SUBCOMMAND_EVENT)
                return [("subcommand", None, lambda: self, "test subcommand")]

        def install():
            executed.append(INSTALL_EVENT)

        self.pluginResults = [
            FakeReactor(install, "fakereactortest", __name__, "described")
        ]

        options = ReactorSelectionOptions()
        options.parseOptions(["--reactor", "fakereactortest", "subcommand"])
        self.assertEqual(executed[0], INSTALL_EVENT)
        self.assertEqual(executed.count(INSTALL_EVENT), 1)
        self.assertEqual(options["reactor"], "fakereactortest")

    def test_reactorSelectionMixinNonExistent(self):
        """
        Test that the usage mixin exits when trying to use a non existent
        reactor (the name not matching to any reactor), giving an error
        message.
        """

        class ReactorSelectionOptions(usage.Options, app.ReactorSelectionMixin):
            pass

        self.pluginResults = []

        options = ReactorSelectionOptions()
        options.messageOutput = StringIO()
        e = self.assertRaises(
            usage.UsageError,
            options.parseOptions,
            ["--reactor", "fakereactortest", "subcommand"],
        )
        self.assertIn("fakereactortest", e.args[0])
        self.assertIn("help-reactors", e.args[0])

    def test_reactorSelectionMixinNotAvailable(self):
        """
        Test that the usage mixin exits when trying to use a reactor not
        available (the reactor raises an error at installation), giving an
        error message.
        """

        class ReactorSelectionOptions(usage.Options, app.ReactorSelectionMixin):
            pass

        message = "Missing foo bar"

        def install():
            raise ImportError(message)

        name = "fakereactortest"
        package = __name__
        description = "description"
        self.pluginResults = [FakeReactor(install, name, package, description)]

        options = ReactorSelectionOptions()
        options.messageOutput = StringIO()
        e = self.assertRaises(
            usage.UsageError,
            options.parseOptions,
            ["--reactor", "fakereactortest", "subcommand"],
        )
        self.assertIn(message, e.args[0])
        self.assertIn("help-reactors", e.args[0])


class HelpReactorsTests(TestCase):
    """
    --help-reactors lists the available reactors
    """

    def setUp(self):
        """
        Get the text from --help-reactors
        """
        self.options = app.ReactorSelectionMixin()
        self.options.messageOutput = StringIO()
        self.assertRaises(SystemExit, self.options.opt_help_reactors)
        self.message = self.options.messageOutput.getvalue()

    @skipIf(asyncio, "Not applicable, asyncio is available")
    def test_lacksAsyncIO(self):
        """
        --help-reactors should NOT display the asyncio reactor on Python < 3.4
        """
        self.assertIn(twisted_reactors.asyncio.description, self.message)
        self.assertIn("!" + twisted_reactors.asyncio.shortName, self.message)

    @skipIf(not asyncio, "asyncio library not available")
    def test_hasAsyncIO(self):
        """
        --help-reactors should display the asyncio reactor on Python >= 3.4
        """
        self.assertIn(twisted_reactors.asyncio.description, self.message)
        self.assertNotIn("!" + twisted_reactors.asyncio.shortName, self.message)

    @skipIf(platformType != "win32", "Test only applicable on Windows")
    def test_iocpWin32(self):
        """
        --help-reactors should display the iocp reactor on Windows
        """
        self.assertIn(twisted_reactors.iocp.description, self.message)
        self.assertNotIn("!" + twisted_reactors.iocp.shortName, self.message)

    @skipIf(platformType == "win32", "Test not applicable on Windows")
    def test_iocpNotWin32(self):
        """
        --help-reactors should NOT display the iocp reactor on Windows
        """
        self.assertIn(twisted_reactors.iocp.description, self.message)
        self.assertIn("!" + twisted_reactors.iocp.shortName, self.message)

    def test_onlySupportedReactors(self):
        """
        --help-reactors with only supported reactors
        """

        def getReactorTypes():
            yield twisted_reactors.default

        options = app.ReactorSelectionMixin()
        options._getReactorTypes = getReactorTypes
        options.messageOutput = StringIO()
        self.assertRaises(SystemExit, options.opt_help_reactors)
        message = options.messageOutput.getvalue()
        self.assertNotIn("reactors not available", message)


class BackoffPolicyTests(TestCase):
    """
    Tests of L{twisted.application.internet.backoffPolicy}
    """

    def test_calculates_correct_values(self):
        """
        Test that L{backoffPolicy()} calculates expected values
        """
        pol = backoffPolicy(1.0, 60.0, 1.5, jitter=lambda: 1)
        self.assertAlmostEqual(pol(0), 2)
        self.assertAlmostEqual(pol(1), 2.5)
        self.assertAlmostEqual(pol(10), 58.6650390625)
        self.assertEqual(pol(20), 61)
        self.assertEqual(pol(100), 61)

    def test_does_not_overflow_on_high_attempts(self):
        """
        L{backoffPolicy()} does not fail for large values of the attempt
        parameter. In previous versions, this test failed when attempt was
        larger than 1750.

        See https://twistedmatrix.com/trac/ticket/9476
        """
        pol = backoffPolicy(1.0, 60.0, 1.5, jitter=lambda: 1)
        self.assertEqual(pol(1751), 61)
        self.assertEqual(pol(1000000), 61)

    def test_does_not_overflow_with_large_factor_value(self):
        """
        Even with unusual parameters, any L{OverflowError} within
        L{backoffPolicy()} will be caught and L{maxDelay} will be returned
        instead
        """
        pol = backoffPolicy(1.0, 60.0, 1e10, jitter=lambda: 1)
        self.assertEqual(pol(1751), 61)

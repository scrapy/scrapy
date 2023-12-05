# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Test cases for Twisted component architecture.
"""


from functools import wraps

from zope.interface import Attribute, Interface, implementer
from zope.interface.adapter import AdapterRegistry

from twisted.python import components
from twisted.python.compat import cmp, comparable
from twisted.python.components import _addHook, _removeHook, proxyForInterface
from twisted.trial import unittest


class Compo(components.Componentized):
    num = 0

    def inc(self):
        self.num = self.num + 1
        return self.num


class IAdept(Interface):
    def adaptorFunc():
        raise NotImplementedError()


class IElapsed(Interface):
    def elapsedFunc():
        """
        1!
        """


@implementer(IAdept)
class Adept(components.Adapter):
    def __init__(self, orig):
        self.original = orig
        self.num = 0

    def adaptorFunc(self):
        self.num = self.num + 1
        return self.num, self.original.inc()


@implementer(IElapsed)
class Elapsed(components.Adapter):
    def elapsedFunc(self):
        return 1


class AComp(components.Componentized):
    pass


class BComp(AComp):
    pass


class CComp(BComp):
    pass


class ITest(Interface):
    pass


class ITest2(Interface):
    pass


class ITest3(Interface):
    pass


class ITest4(Interface):
    pass


@implementer(ITest, ITest3, ITest4)
class Test(components.Adapter):
    def __init__(self, orig):
        pass


@implementer(ITest2)
class Test2:
    temporaryAdapter = 1

    def __init__(self, orig):
        pass


class RegistryUsingMixin:
    """
    Mixin for test cases which modify the global registry somehow.
    """

    def setUp(self):
        """
        Configure L{twisted.python.components.registerAdapter} to mutate an
        alternate registry to improve test isolation.
        """
        # Create a brand new, empty registry and put it onto the components
        # module where registerAdapter will use it.  Also ensure that it goes
        # away at the end of the test.
        scratchRegistry = AdapterRegistry()
        self.patch(components, "globalRegistry", scratchRegistry)
        # Hook the new registry up to the adapter lookup system and ensure that
        # association is also discarded after the test.
        hook = _addHook(scratchRegistry)
        self.addCleanup(_removeHook, hook)


class ComponentizedTests(unittest.SynchronousTestCase, RegistryUsingMixin):
    """
    Simple test case for caching in Componentized.
    """

    def setUp(self):
        RegistryUsingMixin.setUp(self)

        components.registerAdapter(Test, AComp, ITest)
        components.registerAdapter(Test, AComp, ITest3)
        components.registerAdapter(Test2, AComp, ITest2)

    def testComponentized(self):
        components.registerAdapter(Adept, Compo, IAdept)
        components.registerAdapter(Elapsed, Compo, IElapsed)

        c = Compo()
        assert c.getComponent(IAdept).adaptorFunc() == (1, 1)
        assert c.getComponent(IAdept).adaptorFunc() == (2, 2)
        assert IElapsed(IAdept(c)).elapsedFunc() == 1

    def testInheritanceAdaptation(self):
        c = CComp()
        co1 = c.getComponent(ITest)
        co2 = c.getComponent(ITest)
        co3 = c.getComponent(ITest2)
        co4 = c.getComponent(ITest2)
        assert co1 is co2
        assert co3 is not co4
        c.removeComponent(co1)
        co5 = c.getComponent(ITest)
        co6 = c.getComponent(ITest)
        assert co5 is co6
        assert co1 is not co5

    def testMultiAdapter(self):
        c = CComp()
        co1 = c.getComponent(ITest)
        co3 = c.getComponent(ITest3)
        co4 = c.getComponent(ITest4)
        self.assertIsNone(co4)
        self.assertIs(co1, co3)

    def test_getComponentDefaults(self):
        """
        Test that a default value specified to Componentized.getComponent if
        there is no component for the requested interface.
        """
        componentized = components.Componentized()
        default = object()
        self.assertIs(componentized.getComponent(ITest, default), default)
        self.assertIs(componentized.getComponent(ITest, default=default), default)
        self.assertIs(componentized.getComponent(ITest), None)

    def test_setAdapter(self):
        """
        C{Componentized.setAdapter} sets a component for an interface by
        wrapping the instance with the given adapter class.
        """
        componentized = components.Componentized()
        componentized.setAdapter(IAdept, Adept)
        component = componentized.getComponent(IAdept)
        self.assertEqual(component.original, componentized)
        self.assertIsInstance(component, Adept)

    def test_addAdapter(self):
        """
        C{Componentized.setAdapter} adapts the instance by wrapping it with
        given adapter class, then stores it using C{addComponent}.
        """
        componentized = components.Componentized()
        componentized.addAdapter(Adept, ignoreClass=True)
        component = componentized.getComponent(IAdept)
        self.assertEqual(component.original, componentized)
        self.assertIsInstance(component, Adept)

    def test_setComponent(self):
        """
        C{Componentized.setComponent} stores the given component using the
        given interface as the key.
        """
        componentized = components.Componentized()
        obj = object()
        componentized.setComponent(ITest, obj)
        self.assertIs(componentized.getComponent(ITest), obj)

    def test_unsetComponent(self):
        """
        C{Componentized.setComponent} removes the cached component for the
        given interface.
        """
        componentized = components.Componentized()
        obj = object()
        componentized.setComponent(ITest, obj)
        componentized.unsetComponent(ITest)
        self.assertIsNone(componentized.getComponent(ITest))

    def test_reprableComponentized(self):
        """
        C{ReprableComponentized} has a C{__repr__} that lists its cache.
        """
        rc = components.ReprableComponentized()
        rc.setComponent(ITest, "hello")
        result = repr(rc)
        self.assertIn("ITest", result)
        self.assertIn("hello", result)


class AdapterTests(unittest.SynchronousTestCase):
    """Test adapters."""

    def testAdapterGetComponent(self):
        o = object()
        a = Adept(o)
        self.assertRaises(components.CannotAdapt, ITest, a)
        self.assertIsNone(ITest(a, None))


class IMeta(Interface):
    pass


@implementer(IMeta)
class MetaAdder(components.Adapter):
    def add(self, num):
        return self.original.num + num


@implementer(IMeta)
class BackwardsAdder(components.Adapter):
    def add(self, num):
        return self.original.num - num


class MetaNumber:
    """
    Integer wrapper for Interface adaptation tests.
    """

    def __init__(self, num):
        self.num = num


class ComponentNumber(components.Componentized):
    def __init__(self):
        self.num = 0
        components.Componentized.__init__(self)


@implementer(IMeta)
class ComponentAdder(components.Adapter):
    """
    Adder for componentized adapter tests.
    """

    def __init__(self, original):
        components.Adapter.__init__(self, original)
        self.num = self.original.num

    def add(self, num):
        self.num += num
        return self.num


class IAttrX(Interface):
    """
    Base interface for test of adapter with C{__cmp__}.
    """

    def x():
        """
        Return a value.
        """


class IAttrXX(Interface):
    """
    Adapted interface for test of adapter with C{__cmp__}.
    """

    def xx():
        """
        Return a tuple of values.
        """


@implementer(IAttrX)
class Xcellent:
    """
    L{IAttrX} implementation for test of adapter with C{__cmp__}.
    """

    def x(self):
        """
        Return a value.

        @return: a value
        """
        return "x!"


@comparable
class DoubleXAdapter:
    """
    Adapter with __cmp__.
    """

    num = 42

    def __init__(self, original):
        self.original = original

    def xx(self):
        return (self.original.x(), self.original.x())

    def __cmp__(self, other):
        return cmp(self.num, other.num)


class MetaInterfaceTests(RegistryUsingMixin, unittest.SynchronousTestCase):
    def test_basic(self):
        """
        Registered adapters can be used to adapt classes to an interface.
        """
        components.registerAdapter(MetaAdder, MetaNumber, IMeta)
        n = MetaNumber(1)
        self.assertEqual(IMeta(n).add(1), 2)

    def testComponentizedInteraction(self):
        components.registerAdapter(ComponentAdder, ComponentNumber, IMeta)
        c = ComponentNumber()
        IMeta(c).add(1)
        IMeta(c).add(1)
        self.assertEqual(IMeta(c).add(1), 3)

    def testAdapterWithCmp(self):
        # Make sure that a __cmp__ on an adapter doesn't break anything
        components.registerAdapter(DoubleXAdapter, IAttrX, IAttrXX)
        xx = IAttrXX(Xcellent())
        self.assertEqual(("x!", "x!"), xx.xx())


class RegistrationTests(RegistryUsingMixin, unittest.SynchronousTestCase):
    """
    Tests for adapter registration.
    """

    def _registerAdapterForClassOrInterface(self, original):
        """
        Register an adapter with L{components.registerAdapter} for the given
        class or interface and verify that the adapter can be looked up with
        L{components.getAdapterFactory}.
        """
        adapter = lambda o: None
        components.registerAdapter(adapter, original, ITest)
        self.assertIs(components.getAdapterFactory(original, ITest, None), adapter)

    def test_registerAdapterForClass(self):
        """
        Test that an adapter from a class can be registered and then looked
        up.
        """

        class TheOriginal:
            pass

        return self._registerAdapterForClassOrInterface(TheOriginal)

    def test_registerAdapterForInterface(self):
        """
        Test that an adapter from an interface can be registered and then
        looked up.
        """
        return self._registerAdapterForClassOrInterface(ITest2)

    def _duplicateAdapterForClassOrInterface(self, original):
        """
        Verify that L{components.registerAdapter} raises L{ValueError} if the
        from-type/interface and to-interface pair is not unique.
        """
        firstAdapter = lambda o: False
        secondAdapter = lambda o: True
        components.registerAdapter(firstAdapter, original, ITest)
        self.assertRaises(
            ValueError, components.registerAdapter, secondAdapter, original, ITest
        )
        # Make sure that the original adapter is still around as well
        self.assertIs(components.getAdapterFactory(original, ITest, None), firstAdapter)

    def test_duplicateAdapterForClass(self):
        """
        Test that attempting to register a second adapter from a class
        raises the appropriate exception.
        """

        class TheOriginal:
            pass

        return self._duplicateAdapterForClassOrInterface(TheOriginal)

    def test_duplicateAdapterForInterface(self):
        """
        Test that attempting to register a second adapter from an interface
        raises the appropriate exception.
        """
        return self._duplicateAdapterForClassOrInterface(ITest2)

    def _duplicateAdapterForClassOrInterfaceAllowed(self, original):
        """
        Verify that when C{components.ALLOW_DUPLICATES} is set to C{True}, new
        adapter registrations for a particular from-type/interface and
        to-interface pair replace older registrations.
        """
        firstAdapter = lambda o: False
        secondAdapter = lambda o: True

        class TheInterface(Interface):
            pass

        components.registerAdapter(firstAdapter, original, TheInterface)
        components.ALLOW_DUPLICATES = True
        try:
            components.registerAdapter(secondAdapter, original, TheInterface)
            self.assertIs(
                components.getAdapterFactory(original, TheInterface, None),
                secondAdapter,
            )
        finally:
            components.ALLOW_DUPLICATES = False

        # It should be rejected again at this point
        self.assertRaises(
            ValueError, components.registerAdapter, firstAdapter, original, TheInterface
        )

        self.assertIs(
            components.getAdapterFactory(original, TheInterface, None), secondAdapter
        )

    def test_duplicateAdapterForClassAllowed(self):
        """
        Test that when L{components.ALLOW_DUPLICATES} is set to a true
        value, duplicate registrations from classes are allowed to override
        the original registration.
        """

        class TheOriginal:
            pass

        return self._duplicateAdapterForClassOrInterfaceAllowed(TheOriginal)

    def test_duplicateAdapterForInterfaceAllowed(self):
        """
        Test that when L{components.ALLOW_DUPLICATES} is set to a true
        value, duplicate registrations from interfaces are allowed to
        override the original registration.
        """

        class TheOriginal(Interface):
            pass

        return self._duplicateAdapterForClassOrInterfaceAllowed(TheOriginal)

    def _multipleInterfacesForClassOrInterface(self, original):
        """
        Verify that an adapter can be registered for multiple to-interfaces at a
        time.
        """
        adapter = lambda o: None
        components.registerAdapter(adapter, original, ITest, ITest2)
        self.assertIs(components.getAdapterFactory(original, ITest, None), adapter)
        self.assertIs(components.getAdapterFactory(original, ITest2, None), adapter)

    def test_multipleInterfacesForClass(self):
        """
        Test the registration of an adapter from a class to several
        interfaces at once.
        """

        class TheOriginal:
            pass

        return self._multipleInterfacesForClassOrInterface(TheOriginal)

    def test_multipleInterfacesForInterface(self):
        """
        Test the registration of an adapter from an interface to several
        interfaces at once.
        """
        return self._multipleInterfacesForClassOrInterface(ITest3)

    def _subclassAdapterRegistrationForClassOrInterface(self, original):
        """
        Verify that a new adapter can be registered for a particular
        to-interface from a subclass of a type or interface which already has an
        adapter registered to that interface and that the subclass adapter takes
        precedence over the base class adapter.
        """
        firstAdapter = lambda o: True
        secondAdapter = lambda o: False

        class TheSubclass(original):
            pass

        components.registerAdapter(firstAdapter, original, ITest)
        components.registerAdapter(secondAdapter, TheSubclass, ITest)
        self.assertIs(components.getAdapterFactory(original, ITest, None), firstAdapter)
        self.assertIs(
            components.getAdapterFactory(TheSubclass, ITest, None), secondAdapter
        )

    def test_subclassAdapterRegistrationForClass(self):
        """
        Test that an adapter to a particular interface can be registered
        from both a class and its subclass.
        """

        class TheOriginal:
            pass

        return self._subclassAdapterRegistrationForClassOrInterface(TheOriginal)

    def test_subclassAdapterRegistrationForInterface(self):
        """
        Test that an adapter to a particular interface can be registered
        from both an interface and its subclass.
        """
        return self._subclassAdapterRegistrationForClassOrInterface(ITest2)


class IProxiedInterface(Interface):
    """
    An interface class for use by L{proxyForInterface}.
    """

    ifaceAttribute = Attribute(
        """
        An example declared attribute, which should be proxied."""
    )

    def yay(*a, **kw):
        """
        A sample method which should be proxied.
        """


class IProxiedSubInterface(IProxiedInterface):
    """
    An interface that derives from another for use with L{proxyForInterface}.
    """

    def boo():
        """
        A different sample method which should be proxied.
        """


@implementer(IProxiedInterface)
class Yayable:  # type: ignore[misc]
    # class does not implement Attribute ifaceAttribute
    # so we need to turn off mypy warning
    """
    A provider of L{IProxiedInterface} which increments a counter for
    every call to C{yay}.

    @ivar yays: The number of times C{yay} has been called.
    """

    def __init__(self):
        self.yays = 0
        self.yayArgs = []

    def yay(self, *a, **kw):
        """
        Increment C{self.yays}.
        """
        self.yays += 1
        self.yayArgs.append((a, kw))
        return self.yays


@implementer(IProxiedSubInterface)
class Booable:  # type: ignore[misc]
    # class does not implement Attribute ifaceAttribute
    # so we need to turn off mypy warning
    """
    An implementation of IProxiedSubInterface
    """

    yayed = False
    booed = False

    def yay(self, *a, **kw):
        """
        Mark the fact that 'yay' has been called.
        """
        self.yayed = True

    def boo(self):
        """
        Mark the fact that 'boo' has been called.1
        """
        self.booed = True


class IMultipleMethods(Interface):
    """
    An interface with multiple methods.
    """

    def methodOne():
        """
        The first method. Should return 1.
        """

    def methodTwo():
        """
        The second method. Should return 2.
        """


class MultipleMethodImplementor:
    """
    A precise implementation of L{IMultipleMethods}.
    """

    def methodOne(self):
        """
        @return: 1
        """
        return 1

    def methodTwo(self):
        """
        @return: 2
        """
        return 2


class ProxyForInterfaceTests(unittest.SynchronousTestCase):
    """
    Tests for L{proxyForInterface}.
    """

    def test_original(self):
        """
        Proxy objects should have an C{original} attribute which refers to the
        original object passed to the constructor.
        """
        original = object()
        proxy = proxyForInterface(IProxiedInterface)(original)
        self.assertIs(proxy.original, original)

    def test_proxyMethod(self):
        """
        The class created from L{proxyForInterface} passes methods on an
        interface to the object which is passed to its constructor.
        """
        klass = proxyForInterface(IProxiedInterface)
        yayable = Yayable()
        proxy = klass(yayable)
        proxy.yay()
        self.assertEqual(proxy.yay(), 2)
        self.assertEqual(yayable.yays, 2)

    def test_decoratedProxyMethod(self):
        """
        Methods of the class created from L{proxyForInterface} can be used with
        the decorator-helper L{functools.wraps}.
        """
        base = proxyForInterface(IProxiedInterface)

        class klass(base):
            @wraps(base.yay)
            def yay(self):
                self.original.yays += 1
                return base.yay(self)

        original = Yayable()
        yayable = klass(original)
        yayable.yay()
        self.assertEqual(2, original.yays)

    def test_proxyAttribute(self):
        """
        Proxy objects should proxy declared attributes, but not other
        attributes.
        """
        yayable = Yayable()
        yayable.ifaceAttribute = object()
        proxy = proxyForInterface(IProxiedInterface)(yayable)
        self.assertIs(proxy.ifaceAttribute, yayable.ifaceAttribute)
        self.assertRaises(AttributeError, lambda: proxy.yays)

    def test_proxySetAttribute(self):
        """
        The attributes that proxy objects proxy should be assignable and affect
        the original object.
        """
        yayable = Yayable()
        proxy = proxyForInterface(IProxiedInterface)(yayable)
        thingy = object()
        proxy.ifaceAttribute = thingy
        self.assertIs(yayable.ifaceAttribute, thingy)

    def test_proxyDeleteAttribute(self):
        """
        The attributes that proxy objects proxy should be deletable and affect
        the original object.
        """
        yayable = Yayable()
        yayable.ifaceAttribute = None
        proxy = proxyForInterface(IProxiedInterface)(yayable)
        del proxy.ifaceAttribute
        self.assertFalse(hasattr(yayable, "ifaceAttribute"))

    def test_multipleMethods(self):
        """
        [Regression test] The proxy should send its method calls to the correct
        method, not the incorrect one.
        """
        multi = MultipleMethodImplementor()
        proxy = proxyForInterface(IMultipleMethods)(multi)
        self.assertEqual(proxy.methodOne(), 1)
        self.assertEqual(proxy.methodTwo(), 2)

    def test_subclassing(self):
        """
        It is possible to subclass the result of L{proxyForInterface}.
        """

        class SpecializedProxy(proxyForInterface(IProxiedInterface)):
            """
            A specialized proxy which can decrement the number of yays.
            """

            def boo(self):
                """
                Decrement the number of yays.
                """
                self.original.yays -= 1

        yayable = Yayable()
        special = SpecializedProxy(yayable)
        self.assertEqual(yayable.yays, 0)
        special.boo()
        self.assertEqual(yayable.yays, -1)

    def test_proxyName(self):
        """
        The name of a proxy class indicates which interface it proxies.
        """
        proxy = proxyForInterface(IProxiedInterface)
        self.assertEqual(
            proxy.__name__,
            "(Proxy for " "twisted.python.test.test_components.IProxiedInterface)",
        )

    def test_implements(self):
        """
        The resulting proxy implements the interface that it proxies.
        """
        proxy = proxyForInterface(IProxiedInterface)
        self.assertTrue(IProxiedInterface.implementedBy(proxy))

    def test_proxyDescriptorGet(self):
        """
        _ProxyDescriptor's __get__ method should return the appropriate
        attribute of its argument's 'original' attribute if it is invoked with
        an object.  If it is invoked with None, it should return a false
        class-method emulator instead.

        For some reason, Python's documentation recommends to define
        descriptors' __get__ methods with the 'type' parameter as optional,
        despite the fact that Python itself never actually calls the descriptor
        that way.  This is probably do to support 'foo.__get__(bar)' as an
        idiom.  Let's make sure that the behavior is correct.  Since we don't
        actually use the 'type' argument at all, this test calls it the
        idiomatic way to ensure that signature works; test_proxyInheritance
        verifies the how-Python-actually-calls-it signature.
        """

        class Sample:
            called = False

            def hello(self):
                self.called = True

        fakeProxy = Sample()
        testObject = Sample()
        fakeProxy.original = testObject
        pd = components._ProxyDescriptor("hello", "original")
        self.assertEqual(pd.__get__(fakeProxy), testObject.hello)
        fakeClassMethod = pd.__get__(None)
        fakeClassMethod(fakeProxy)
        self.assertTrue(testObject.called)

    def test_proxyInheritance(self):
        """
        Subclasses of the class returned from L{proxyForInterface} should be
        able to upcall methods by reference to their superclass, as any normal
        Python class can.
        """

        class YayableWrapper(proxyForInterface(IProxiedInterface)):
            """
            This class does not override any functionality.
            """

        class EnhancedWrapper(YayableWrapper):
            """
            This class overrides the 'yay' method.
            """

            wrappedYays = 1

            def yay(self, *a, **k):
                self.wrappedYays += 1
                return YayableWrapper.yay(self, *a, **k) + 7

        yayable = Yayable()
        wrapper = EnhancedWrapper(yayable)
        self.assertEqual(wrapper.yay(3, 4, x=5, y=6), 8)
        self.assertEqual(yayable.yayArgs, [((3, 4), dict(x=5, y=6))])

    def test_interfaceInheritance(self):
        """
        Proxies of subinterfaces generated with proxyForInterface should allow
        access to attributes of both the child and the base interfaces.
        """
        proxyClass = proxyForInterface(IProxiedSubInterface)
        booable = Booable()
        proxy = proxyClass(booable)
        proxy.yay()
        proxy.boo()
        self.assertTrue(booable.yayed)
        self.assertTrue(booable.booed)

    def test_attributeCustomization(self):
        """
        The original attribute name can be customized via the
        C{originalAttribute} argument of L{proxyForInterface}: the attribute
        should change, but the methods of the original object should still be
        callable, and the attributes still accessible.
        """
        yayable = Yayable()
        yayable.ifaceAttribute = object()
        proxy = proxyForInterface(IProxiedInterface, originalAttribute="foo")(yayable)
        self.assertIs(proxy.foo, yayable)

        # Check the behavior
        self.assertEqual(proxy.yay(), 1)
        self.assertIs(proxy.ifaceAttribute, yayable.ifaceAttribute)
        thingy = object()
        proxy.ifaceAttribute = thingy
        self.assertIs(yayable.ifaceAttribute, thingy)
        del proxy.ifaceAttribute
        self.assertFalse(hasattr(yayable, "ifaceAttribute"))

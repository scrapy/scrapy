# -*- test-case-name: twisted.python.test.test_components -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Component architecture for Twisted, based on Zope3 components.

Using the Zope3 API directly is strongly recommended. Everything
you need is in the top-level of the zope.interface package, e.g.::

   from zope.interface import Interface, implementer

   class IFoo(Interface):
       pass

   @implementer(IFoo)
   class Foo:
       pass

   print(IFoo.implementedBy(Foo)) # True
   print(IFoo.providedBy(Foo())) # True

L{twisted.python.components.registerAdapter} from this module may be used to
add to Twisted's global adapter registry.

L{twisted.python.components.proxyForInterface} is a factory for classes
which allow access to only the parts of another class defined by a specified
interface.
"""


from io import StringIO
from typing import Dict

# zope3 imports
from zope.interface import declarations, interface
from zope.interface.adapter import AdapterRegistry

# twisted imports
from twisted.python import reflect

# Twisted's global adapter registry
globalRegistry = AdapterRegistry()

# Attribute that registerAdapter looks at. Is this supposed to be public?
ALLOW_DUPLICATES = 0


def registerAdapter(adapterFactory, origInterface, *interfaceClasses):
    """Register an adapter class.

    An adapter class is expected to implement the given interface, by
    adapting instances implementing 'origInterface'. An adapter class's
    __init__ method should accept one parameter, an instance implementing
    'origInterface'.
    """
    self = globalRegistry
    assert interfaceClasses, "You need to pass an Interface"
    global ALLOW_DUPLICATES

    # deal with class->interface adapters:
    if not isinstance(origInterface, interface.InterfaceClass):
        origInterface = declarations.implementedBy(origInterface)

    for interfaceClass in interfaceClasses:
        factory = self.registered([origInterface], interfaceClass)
        if factory is not None and not ALLOW_DUPLICATES:
            raise ValueError(f"an adapter ({factory}) was already registered.")
    for interfaceClass in interfaceClasses:
        self.register([origInterface], interfaceClass, "", adapterFactory)


def getAdapterFactory(fromInterface, toInterface, default):
    """Return registered adapter for a given class and interface.

    Note that is tied to the *Twisted* global registry, and will
    thus not find adapters registered elsewhere.
    """
    self = globalRegistry
    if not isinstance(fromInterface, interface.InterfaceClass):
        fromInterface = declarations.implementedBy(fromInterface)
    factory = self.lookup1(fromInterface, toInterface)  # type: ignore[attr-defined]
    if factory is None:
        factory = default
    return factory


def _addHook(registry):
    """
    Add an adapter hook which will attempt to look up adapters in the given
    registry.

    @type registry: L{zope.interface.adapter.AdapterRegistry}

    @return: The hook which was added, for later use with L{_removeHook}.
    """
    lookup = registry.lookup1

    def _hook(iface, ob):
        factory = lookup(declarations.providedBy(ob), iface)
        if factory is None:
            return None
        else:
            return factory(ob)

    interface.adapter_hooks.append(_hook)
    return _hook


def _removeHook(hook):
    """
    Remove a previously added adapter hook.

    @param hook: An object previously returned by a call to L{_addHook}.  This
        will be removed from the list of adapter hooks.
    """
    interface.adapter_hooks.remove(hook)


# add global adapter lookup hook for our newly created registry
_addHook(globalRegistry)


def getRegistry():
    """Returns the Twisted global
    C{zope.interface.adapter.AdapterRegistry} instance.
    """
    return globalRegistry


# FIXME: deprecate attribute somehow?
CannotAdapt = TypeError


class Adapter:
    """I am the default implementation of an Adapter for some interface.

    This docstring contains a limerick, by popular demand::

        Subclassing made Zope and TR
        much harder to work with by far.
            So before you inherit,
            be sure to declare it
        Adapter, not PyObject*

    @cvar temporaryAdapter: If this is True, the adapter will not be
          persisted on the Componentized.
    @cvar multiComponent: If this adapter is persistent, should it be
          automatically registered for all appropriate interfaces.
    """

    # These attributes are used with Componentized.

    temporaryAdapter = 0
    multiComponent = 1

    def __init__(self, original):
        """Set my 'original' attribute to be the object I am adapting."""
        self.original = original

    def __conform__(self, interface):
        """
        I forward __conform__ to self.original if it has it, otherwise I
        simply return None.
        """
        if hasattr(self.original, "__conform__"):
            return self.original.__conform__(interface)
        return None

    def isuper(self, iface, adapter):
        """
        Forward isuper to self.original
        """
        return self.original.isuper(iface, adapter)


class Componentized:
    """I am a mixin to allow you to be adapted in various ways persistently.

    I define a list of persistent adapters.  This is to allow adapter classes
    to store system-specific state, and initialized on demand.  The
    getComponent method implements this.  You must also register adapters for
    this class for the interfaces that you wish to pass to getComponent.

    Many other classes and utilities listed here are present in Zope3; this one
    is specific to Twisted.
    """

    persistenceVersion = 1

    def __init__(self):
        self._adapterCache = {}

    def locateAdapterClass(self, klass, interfaceClass, default):
        return getAdapterFactory(klass, interfaceClass, default)

    def setAdapter(self, interfaceClass, adapterClass):
        """
        Cache a provider for the given interface, by adapting C{self} using
        the given adapter class.
        """
        self.setComponent(interfaceClass, adapterClass(self))

    def addAdapter(self, adapterClass, ignoreClass=0):
        """Utility method that calls addComponent.  I take an adapter class and
        instantiate it with myself as the first argument.

        @return: The adapter instantiated.
        """
        adapt = adapterClass(self)
        self.addComponent(adapt, ignoreClass)
        return adapt

    def setComponent(self, interfaceClass, component):
        """
        Cache a provider of the given interface.
        """
        self._adapterCache[reflect.qual(interfaceClass)] = component

    def addComponent(self, component, ignoreClass=0):
        """
        Add a component to me, for all appropriate interfaces.

        In order to determine which interfaces are appropriate, the component's
        provided interfaces will be scanned.

        If the argument 'ignoreClass' is True, then all interfaces are
        considered appropriate.

        Otherwise, an 'appropriate' interface is one for which its class has
        been registered as an adapter for my class according to the rules of
        getComponent.
        """
        for iface in declarations.providedBy(component):
            if ignoreClass or (
                self.locateAdapterClass(self.__class__, iface, None)
                == component.__class__
            ):
                self._adapterCache[reflect.qual(iface)] = component

    def unsetComponent(self, interfaceClass):
        """Remove my component specified by the given interface class."""
        del self._adapterCache[reflect.qual(interfaceClass)]

    def removeComponent(self, component):
        """
        Remove the given component from me entirely, for all interfaces for which
        it has been registered.

        @return: a list of the interfaces that were removed.
        """
        l = []
        for k, v in list(self._adapterCache.items()):
            if v is component:
                del self._adapterCache[k]
                l.append(reflect.namedObject(k))
        return l

    def getComponent(self, interface, default=None):
        """Create or retrieve an adapter for the given interface.

        If such an adapter has already been created, retrieve it from the cache
        that this instance keeps of all its adapters.  Adapters created through
        this mechanism may safely store system-specific state.

        If you want to register an adapter that will be created through
        getComponent, but you don't require (or don't want) your adapter to be
        cached and kept alive for the lifetime of this Componentized object,
        set the attribute 'temporaryAdapter' to True on your adapter class.

        If you want to automatically register an adapter for all appropriate
        interfaces (with addComponent), set the attribute 'multiComponent' to
        True on your adapter class.
        """
        k = reflect.qual(interface)
        if k in self._adapterCache:
            return self._adapterCache[k]
        else:
            adapter = interface.__adapt__(self)
            if adapter is not None and not (
                hasattr(adapter, "temporaryAdapter") and adapter.temporaryAdapter
            ):
                self._adapterCache[k] = adapter
                if hasattr(adapter, "multiComponent") and adapter.multiComponent:
                    self.addComponent(adapter)
            if adapter is None:
                return default
            return adapter

    def __conform__(self, interface):
        return self.getComponent(interface)


class ReprableComponentized(Componentized):
    def __init__(self):
        Componentized.__init__(self)

    def __repr__(self) -> str:
        from pprint import pprint

        sio = StringIO()
        pprint(self._adapterCache, sio)
        return sio.getvalue()


def proxyForInterface(iface, originalAttribute="original"):
    """
    Create a class which proxies all method calls which adhere to an interface
    to another provider of that interface.

    This function is intended for creating specialized proxies. The typical way
    to use it is by subclassing the result::

      class MySpecializedProxy(proxyForInterface(IFoo)):
          def someInterfaceMethod(self, arg):
              if arg == 3:
                  return 3
              return self.original.someInterfaceMethod(arg)

    @param iface: The Interface to which the resulting object will conform, and
        which the wrapped object must provide.

    @param originalAttribute: name of the attribute used to save the original
        object in the resulting class. Default to C{original}.
    @type originalAttribute: C{str}

    @return: A class whose constructor takes the original object as its only
        argument. Constructing the class creates the proxy.
    """

    def __init__(self, original):
        setattr(self, originalAttribute, original)

    contents: Dict[str, object] = {"__init__": __init__}
    for name in iface:
        contents[name] = _ProxyDescriptor(name, originalAttribute)
    proxy = type(f"(Proxy for {reflect.qual(iface)})", (object,), contents)
    # mypy-zope declarations.classImplements only works when passing
    # a concrete class type
    declarations.classImplements(proxy, iface)  # type: ignore[misc]
    return proxy


class _ProxiedClassMethod:
    """
    A proxied class method.

    @ivar methodName: the name of the method which this should invoke when
        called.
    @type methodName: L{str}

    @ivar __name__: The name of the method being proxied (the same as
        C{methodName}).
    @type __name__: L{str}

    @ivar originalAttribute: name of the attribute of the proxy where the
        original object is stored.
    @type originalAttribute: L{str}
    """

    def __init__(self, methodName, originalAttribute):
        self.methodName = self.__name__ = methodName
        self.originalAttribute = originalAttribute

    def __call__(self, oself, *args, **kw):
        """
        Invoke the specified L{methodName} method of the C{original} attribute
        for proxyForInterface.

        @param oself: an instance of a L{proxyForInterface} object.

        @return: the result of the underlying method.
        """
        original = getattr(oself, self.originalAttribute)
        actualMethod = getattr(original, self.methodName)
        return actualMethod(*args, **kw)


class _ProxyDescriptor:
    """
    A descriptor which will proxy attribute access, mutation, and
    deletion to the L{_ProxyDescriptor.originalAttribute} of the
    object it is being accessed from.

    @ivar attributeName: the name of the attribute which this descriptor will
        retrieve from instances' C{original} attribute.
    @type attributeName: C{str}

    @ivar originalAttribute: name of the attribute of the proxy where the
        original object is stored.
    @type originalAttribute: C{str}
    """

    def __init__(self, attributeName, originalAttribute):
        self.attributeName = attributeName
        self.originalAttribute = originalAttribute

    def __get__(self, oself, type=None):
        """
        Retrieve the C{self.attributeName} property from I{oself}.
        """
        if oself is None:
            return _ProxiedClassMethod(self.attributeName, self.originalAttribute)
        original = getattr(oself, self.originalAttribute)
        return getattr(original, self.attributeName)

    def __set__(self, oself, value):
        """
        Set the C{self.attributeName} property of I{oself}.
        """
        original = getattr(oself, self.originalAttribute)
        setattr(original, self.attributeName, value)

    def __delete__(self, oself):
        """
        Delete the C{self.attributeName} property of I{oself}.
        """
        original = getattr(oself, self.originalAttribute)
        delattr(original, self.attributeName)


__all__ = [
    "registerAdapter",
    "getAdapterFactory",
    "Adapter",
    "Componentized",
    "ReprableComponentized",
    "getRegistry",
    "proxyForInterface",
]

##############################################################################
# Copyright (c) 2003 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
##############################################################################
"""Implementation of interface declarations

There are three flavors of declarations:

  - Declarations are used to simply name declared interfaces.

  - ImplementsDeclarations are used to express the interfaces that a
    class implements (that instances of the class provides).

    Implements specifications support inheriting interfaces.

  - ProvidesDeclarations are used to express interfaces directly
    provided by objects.

"""
__docformat__ = 'restructuredtext'

import sys
from types import FunctionType
from types import MethodType
from types import ModuleType
import weakref

from zope.interface.advice import addClassAdvisor
from zope.interface.interface import InterfaceClass
from zope.interface.interface import SpecificationBase
from zope.interface.interface import Specification
from zope.interface._compat import CLASS_TYPES as DescriptorAwareMetaClasses
from zope.interface._compat import PYTHON3

# Registry of class-implementation specifications
BuiltinImplementationSpecifications = {}

_ADVICE_ERROR = ('Class advice impossible in Python3.  '
                 'Use the @%s class decorator instead.')

_ADVICE_WARNING = ('The %s API is deprecated, and will not work in Python3  '
                   'Use the @%s class decorator instead.')

class named(object):

    def __init__(self, name):
        self.name = name

    def __call__(self, ob):
        ob.__component_name__ = self.name
        return ob

class Declaration(Specification):
    """Interface declarations"""

    def __init__(self, *interfaces):
        Specification.__init__(self, _normalizeargs(interfaces))

    def changed(self, originally_changed):
        Specification.changed(self, originally_changed)
        try:
            del self._v_attrs
        except AttributeError:
            pass

    def __contains__(self, interface):
        """Test whether an interface is in the specification
        """

        return self.extends(interface) and interface in self.interfaces()

    def __iter__(self):
        """Return an iterator for the interfaces in the specification
        """
        return self.interfaces()

    def flattened(self):
        """Return an iterator of all included and extended interfaces
        """
        return iter(self.__iro__)

    def __sub__(self, other):
        """Remove interfaces from a specification
        """
        return Declaration(
            *[i for i in self.interfaces()
                if not [j for j in other.interfaces()
                        if i.extends(j, 0)]
                ]
                )

    def __add__(self, other):
        """Add two specifications or a specification and an interface
        """
        seen = {}
        result = []
        for i in self.interfaces():
            seen[i] = 1
            result.append(i)
        for i in other.interfaces():
            if i not in seen:
                seen[i] = 1
                result.append(i)

        return Declaration(*result)

    __radd__ = __add__


##############################################################################
#
# Implementation specifications
#
# These specify interfaces implemented by instances of classes

class Implements(Declaration):

    # class whose specification should be used as additional base
    inherit = None

    # interfaces actually declared for a class
    declared = ()

    __name__ = '?'

    @classmethod
    def named(cls, name, *interfaces):
        # Implementation method: Produce an Implements interface with
        # a fully fleshed out __name__ before calling the constructor, which
        # sets bases to the given interfaces and which may pass this object to
        # other objects (e.g., to adjust dependents). If they're sorting or comparing
        # by name, this needs to be set.
        inst = cls.__new__(cls)
        inst.__name__ = name
        inst.__init__(*interfaces)
        return inst

    def __repr__(self):
        return '<implementedBy %s>' % (self.__name__)

    def __reduce__(self):
        return implementedBy, (self.inherit, )

    def __cmp(self, other):
        # Yes, I did mean to name this __cmp, rather than __cmp__.
        # It is a private method used by __lt__ and __gt__.
        # This is based on, and compatible with, InterfaceClass.
        # (The two must be mutually comparable to be able to work in e.g., BTrees.)
        # Instances of this class generally don't have a __module__ other than
        # `zope.interface.declarations`, whereas they *do* have a __name__ that is the
        # fully qualified name of the object they are representing.

        # Note, though, that equality and hashing are still identity based. This
        # accounts for things like nested objects that have the same name (typically
        # only in tests) and is consistent with pickling. As far as comparisons to InterfaceClass
        # goes, we'll never have equal name and module to those, so we're still consistent there.
        # Instances of this class are essentially intended to be unique and are
        # heavily cached (note how our __reduce__ handles this) so having identity
        # based hash and eq should also work.
        if other is None:
            return -1

        n1 = (self.__name__, self.__module__)
        n2 = (getattr(other, '__name__', ''), getattr(other,  '__module__', ''))

        # This spelling works under Python3, which doesn't have cmp().
        return (n1 > n2) - (n1 < n2)

    def __hash__(self):
        return Declaration.__hash__(self)

    # We want equality to be based on identity. However, we can't actually
    # implement __eq__/__ne__ to do this because sometimes we get wrapped in a proxy.
    # We need to let the proxy types implement these methods so they can handle unwrapping
    # and then rely on: (1) the interpreter automatically changing `implements == proxy` into
    # `proxy == implements` (which will call proxy.__eq__ to do the unwrapping) and then
    # (2) the default equality semantics being identity based.

    def __lt__(self, other):
        c = self.__cmp(other)
        return c < 0

    def __le__(self, other):
        c = self.__cmp(other)
        return c <= 0

    def __gt__(self, other):
        c = self.__cmp(other)
        return c > 0

    def __ge__(self, other):
        c = self.__cmp(other)
        return c >= 0

def _implements_name(ob):
    # Return the __name__ attribute to be used by its __implemented__
    # property.
    # This must be stable for the "same" object across processes
    # because it is used for sorting. It needn't be unique, though, in cases
    # like nested classes named Foo created by different functions, because
    # equality and hashing is still based on identity.
    # It might be nice to use __qualname__ on Python 3, but that would produce
    # different values between Py2 and Py3.
    return (getattr(ob, '__module__', '?') or '?') + \
        '.' + (getattr(ob, '__name__', '?') or '?')

def implementedByFallback(cls):
    """Return the interfaces implemented for a class' instances

      The value returned is an IDeclaration.
    """
    try:
        spec = cls.__dict__.get('__implemented__')
    except AttributeError:

        # we can't get the class dict. This is probably due to a
        # security proxy.  If this is the case, then probably no
        # descriptor was installed for the class.

        # We don't want to depend directly on zope.security in
        # zope.interface, but we'll try to make reasonable
        # accommodations in an indirect way.

        # We'll check to see if there's an implements:

        spec = getattr(cls, '__implemented__', None)
        if spec is None:
            # There's no spec stred in the class. Maybe its a builtin:
            spec = BuiltinImplementationSpecifications.get(cls)
            if spec is not None:
                return spec
            return _empty

        if spec.__class__ == Implements:
            # we defaulted to _empty or there was a spec. Good enough.
            # Return it.
            return spec

        # TODO: need old style __implements__ compatibility?
        # Hm, there's an __implemented__, but it's not a spec. Must be
        # an old-style declaration. Just compute a spec for it
        return Declaration(*_normalizeargs((spec, )))

    if isinstance(spec, Implements):
        return spec

    if spec is None:
        spec = BuiltinImplementationSpecifications.get(cls)
        if spec is not None:
            return spec

    # TODO: need old style __implements__ compatibility?
    spec_name = _implements_name(cls)
    if spec is not None:
        # old-style __implemented__ = foo declaration
        spec = (spec, ) # tuplefy, as it might be just an int
        spec = Implements.named(spec_name, *_normalizeargs(spec))
        spec.inherit = None    # old-style implies no inherit
        del cls.__implemented__ # get rid of the old-style declaration
    else:
        try:
            bases = cls.__bases__
        except AttributeError:
            if not callable(cls):
                raise TypeError("ImplementedBy called for non-factory", cls)
            bases = ()

        spec = Implements.named(spec_name, *[implementedBy(c) for c in bases])
        spec.inherit = cls

    try:
        cls.__implemented__ = spec
        if not hasattr(cls, '__providedBy__'):
            cls.__providedBy__ = objectSpecificationDescriptor

        if (isinstance(cls, DescriptorAwareMetaClasses)
            and
            '__provides__' not in cls.__dict__):
            # Make sure we get a __provides__ descriptor
            cls.__provides__ = ClassProvides(
                cls,
                getattr(cls, '__class__', type(cls)),
                )

    except TypeError:
        if not isinstance(cls, type):
            raise TypeError("ImplementedBy called for non-type", cls)
        BuiltinImplementationSpecifications[cls] = spec

    return spec

implementedBy = implementedByFallback

def classImplementsOnly(cls, *interfaces):
    """Declare the only interfaces implemented by instances of a class

      The arguments after the class are one or more interfaces or interface
      specifications (``IDeclaration`` objects).

      The interfaces given (including the interfaces in the specifications)
      replace any previous declarations.
    """
    spec = implementedBy(cls)
    spec.declared = ()
    spec.inherit = None
    classImplements(cls, *interfaces)

def classImplements(cls, *interfaces):
    """Declare additional interfaces implemented for instances of a class

      The arguments after the class are one or more interfaces or
      interface specifications (``IDeclaration`` objects).

      The interfaces given (including the interfaces in the specifications)
      are added to any interfaces previously declared.
    """
    spec = implementedBy(cls)
    spec.declared += tuple(_normalizeargs(interfaces))

    # compute the bases
    bases = []
    seen = {}
    for b in spec.declared:
        if b not in seen:
            seen[b] = 1
            bases.append(b)

    if spec.inherit is not None:

        for c in spec.inherit.__bases__:
            b = implementedBy(c)
            if b not in seen:
                seen[b] = 1
                bases.append(b)

    spec.__bases__ = tuple(bases)

def _implements_advice(cls):
    interfaces, classImplements = cls.__dict__['__implements_advice_data__']
    del cls.__implements_advice_data__
    classImplements(cls, *interfaces)
    return cls


class implementer:
    """Declare the interfaces implemented by instances of a class.

      This function is called as a class decorator.

      The arguments are one or more interfaces or interface
      specifications (IDeclaration objects).

      The interfaces given (including the interfaces in the
      specifications) are added to any interfaces previously
      declared.

      Previous declarations include declarations for base classes
      unless implementsOnly was used.

      This function is provided for convenience. It provides a more
      convenient way to call classImplements. For example::

        @implementer(I1)
        class C(object):
            pass

      is equivalent to calling::

        classImplements(C, I1)

      after the class has been created.
      """

    def __init__(self, *interfaces):
        self.interfaces = interfaces

    def __call__(self, ob):
        if isinstance(ob, DescriptorAwareMetaClasses):
            classImplements(ob, *self.interfaces)
            return ob

        spec_name = _implements_name(ob)
        spec = Implements.named(spec_name, *self.interfaces)
        try:
            ob.__implemented__ = spec
        except AttributeError:
            raise TypeError("Can't declare implements", ob)
        return ob

class implementer_only:
    """Declare the only interfaces implemented by instances of a class

      This function is called as a class decorator.

      The arguments are one or more interfaces or interface
      specifications (IDeclaration objects).

      Previous declarations including declarations for base classes
      are overridden.

      This function is provided for convenience. It provides a more
      convenient way to call classImplementsOnly. For example::

        @implementer_only(I1)
        class C(object): pass

      is equivalent to calling::

        classImplementsOnly(I1)

      after the class has been created.
      """

    def __init__(self, *interfaces):
        self.interfaces = interfaces

    def __call__(self, ob):
        if isinstance(ob, (FunctionType, MethodType)):
            # XXX Does this decorator make sense for anything but classes?
            # I don't think so. There can be no inheritance of interfaces
            # on a method pr function....
            raise ValueError('The implementer_only decorator is not '
                             'supported for methods or functions.')
        else:
            # Assume it's a class:
            classImplementsOnly(ob, *self.interfaces)
            return ob

def _implements(name, interfaces, classImplements):
    # This entire approach is invalid under Py3K.  Don't even try to fix
    # the coverage for this block there. :(
    if PYTHON3: #pragma NO COVER
        raise TypeError('Class advice impossible in Python3')
    frame = sys._getframe(2)
    locals = frame.f_locals

    # Try to make sure we were called from a class def. In 2.2.0 we can't
    # check for __module__ since it doesn't seem to be added to the locals
    # until later on.
    if locals is frame.f_globals or '__module__' not in locals:
        raise TypeError(name+" can be used only from a class definition.")

    if '__implements_advice_data__' in locals:
        raise TypeError(name+" can be used only once in a class definition.")

    locals['__implements_advice_data__'] = interfaces, classImplements
    addClassAdvisor(_implements_advice, depth=3)

def implements(*interfaces):
    """Declare interfaces implemented by instances of a class

      This function is called in a class definition.

      The arguments are one or more interfaces or interface
      specifications (IDeclaration objects).

      The interfaces given (including the interfaces in the
      specifications) are added to any interfaces previously
      declared.

      Previous declarations include declarations for base classes
      unless implementsOnly was used.

      This function is provided for convenience. It provides a more
      convenient way to call classImplements. For example::

        implements(I1)

      is equivalent to calling::

        classImplements(C, I1)

      after the class has been created.
    """
    # This entire approach is invalid under Py3K.  Don't even try to fix
    # the coverage for this block there. :(
    if PYTHON3: #pragma NO COVER
        raise TypeError(_ADVICE_ERROR % 'implementer')
    _implements("implements", interfaces, classImplements)

def implementsOnly(*interfaces):
    """Declare the only interfaces implemented by instances of a class

      This function is called in a class definition.

      The arguments are one or more interfaces or interface
      specifications (IDeclaration objects).

      Previous declarations including declarations for base classes
      are overridden.

      This function is provided for convenience. It provides a more
      convenient way to call classImplementsOnly. For example::

        implementsOnly(I1)

      is equivalent to calling::

        classImplementsOnly(I1)

      after the class has been created.
    """
    # This entire approach is invalid under Py3K.  Don't even try to fix
    # the coverage for this block there. :(
    if PYTHON3: #pragma NO COVER
        raise TypeError(_ADVICE_ERROR % 'implementer_only')
    _implements("implementsOnly", interfaces, classImplementsOnly)

##############################################################################
#
# Instance declarations

class Provides(Declaration):  # Really named ProvidesClass
    """Implement __provides__, the instance-specific specification

    When an object is pickled, we pickle the interfaces that it implements.
    """

    def __init__(self, cls, *interfaces):
        self.__args = (cls, ) + interfaces
        self._cls = cls
        Declaration.__init__(self, *(interfaces + (implementedBy(cls), )))

    def __reduce__(self):
        return Provides, self.__args

    __module__ = 'zope.interface'

    def __get__(self, inst, cls):
        """Make sure that a class __provides__ doesn't leak to an instance
        """
        if inst is None and cls is self._cls:
            # We were accessed through a class, so we are the class'
            # provides spec. Just return this object, but only if we are
            # being called on the same class that we were defined for:
            return self

        raise AttributeError('__provides__')

ProvidesClass = Provides

# Registry of instance declarations
# This is a memory optimization to allow objects to share specifications.
InstanceDeclarations = weakref.WeakValueDictionary()

def Provides(*interfaces):
    """Cache instance declarations

      Instance declarations are shared among instances that have the same
      declaration. The declarations are cached in a weak value dictionary.
    """
    spec = InstanceDeclarations.get(interfaces)
    if spec is None:
        spec = ProvidesClass(*interfaces)
        InstanceDeclarations[interfaces] = spec

    return spec

Provides.__safe_for_unpickling__ = True


def directlyProvides(object, *interfaces):
    """Declare interfaces declared directly for an object

      The arguments after the object are one or more interfaces or interface
      specifications (``IDeclaration`` objects).

      The interfaces given (including the interfaces in the specifications)
      replace interfaces previously declared for the object.
    """
    cls = getattr(object, '__class__', None)
    if cls is not None and getattr(cls,  '__class__', None) is cls:
        # It's a meta class (well, at least it it could be an extension class)
        # Note that we can't get here from Py3k tests:  there is no normal
        # class which isn't descriptor aware.
        if not isinstance(object,
                          DescriptorAwareMetaClasses): #pragma NO COVER Py3k
            raise TypeError("Attempt to make an interface declaration on a "
                            "non-descriptor-aware class")

    interfaces = _normalizeargs(interfaces)
    if cls is None:
        cls = type(object)

    issub = False
    for damc in DescriptorAwareMetaClasses:
        if issubclass(cls, damc):
            issub = True
            break
    if issub:
        # we have a class or type.  We'll use a special descriptor
        # that provides some extra caching
        object.__provides__ = ClassProvides(object, cls, *interfaces)
    else:
        object.__provides__ = Provides(cls, *interfaces)


def alsoProvides(object, *interfaces):
    """Declare interfaces declared directly for an object

    The arguments after the object are one or more interfaces or interface
    specifications (``IDeclaration`` objects).

    The interfaces given (including the interfaces in the specifications) are
    added to the interfaces previously declared for the object.
    """
    directlyProvides(object, directlyProvidedBy(object), *interfaces)

def noLongerProvides(object, interface):
    """ Removes a directly provided interface from an object.
    """
    directlyProvides(object, directlyProvidedBy(object) - interface)
    if interface.providedBy(object):
        raise ValueError("Can only remove directly provided interfaces.")

class ClassProvidesBaseFallback(object):

    def __get__(self, inst, cls):
        if cls is self._cls:
            # We only work if called on the class we were defined for

            if inst is None:
                # We were accessed through a class, so we are the class'
                # provides spec. Just return this object as is:
                return self

            return self._implements

        raise AttributeError('__provides__')

ClassProvidesBasePy = ClassProvidesBaseFallback # BBB
ClassProvidesBase = ClassProvidesBaseFallback

# Try to get C base:
try:
    import _zope_interface_coptimizations
except ImportError:  #pragma NO COVERAGE
    pass
else:  #pragma NO COVERAGE
    from _zope_interface_coptimizations import ClassProvidesBase


class ClassProvides(Declaration, ClassProvidesBase):
    """Special descriptor for class __provides__

    The descriptor caches the implementedBy info, so that
    we can get declarations for objects without instance-specific
    interfaces a bit quicker.
    """
    def __init__(self, cls, metacls, *interfaces):
        self._cls = cls
        self._implements = implementedBy(cls)
        self.__args = (cls, metacls, ) + interfaces
        Declaration.__init__(self, *(interfaces + (implementedBy(metacls), )))

    def __reduce__(self):
        return self.__class__, self.__args

    # Copy base-class method for speed
    __get__ = ClassProvidesBase.__get__

def directlyProvidedBy(object):
    """Return the interfaces directly provided by the given object

    The value returned is an ``IDeclaration``.
    """
    provides = getattr(object, "__provides__", None)
    if (provides is None # no spec
        or
        # We might have gotten the implements spec, as an
        # optimization. If so, it's like having only one base, that we
        # lop off to exclude class-supplied declarations:
        isinstance(provides, Implements)
        ):
        return _empty

    # Strip off the class part of the spec:
    return Declaration(provides.__bases__[:-1])

def classProvides(*interfaces):
    """Declare interfaces provided directly by a class

      This function is called in a class definition.

      The arguments are one or more interfaces or interface specifications
      (``IDeclaration`` objects).

      The given interfaces (including the interfaces in the specifications)
      are used to create the class's direct-object interface specification.
      An error will be raised if the module class has an direct interface
      specification. In other words, it is an error to call this function more
      than once in a class definition.

      Note that the given interfaces have nothing to do with the interfaces
      implemented by instances of the class.

      This function is provided for convenience. It provides a more convenient
      way to call directlyProvides for a class. For example::

        classProvides(I1)

      is equivalent to calling::

        directlyProvides(theclass, I1)

      after the class has been created.
    """
    # This entire approach is invalid under Py3K.  Don't even try to fix
    # the coverage for this block there. :(

    if PYTHON3: #pragma NO COVER
        raise TypeError(_ADVICE_ERROR % 'provider')

    frame = sys._getframe(1)
    locals = frame.f_locals

    # Try to make sure we were called from a class def
    if (locals is frame.f_globals) or ('__module__' not in locals):
        raise TypeError("classProvides can be used only from a "
                        "class definition.")

    if '__provides__' in locals:
        raise TypeError(
            "classProvides can only be used once in a class definition.")

    locals["__provides__"] = _normalizeargs(interfaces)

    addClassAdvisor(_classProvides_advice, depth=2)

def _classProvides_advice(cls):
    # This entire approach is invalid under Py3K.  Don't even try to fix
    # the coverage for this block there. :(
    interfaces = cls.__dict__['__provides__']
    del cls.__provides__
    directlyProvides(cls, *interfaces)
    return cls

class provider:
    """Class decorator version of classProvides"""

    def __init__(self, *interfaces):
        self.interfaces = interfaces

    def __call__(self, ob):
        directlyProvides(ob, *self.interfaces)
        return ob

def moduleProvides(*interfaces):
    """Declare interfaces provided by a module

    This function is used in a module definition.

    The arguments are one or more interfaces or interface specifications
    (``IDeclaration`` objects).

    The given interfaces (including the interfaces in the specifications) are
    used to create the module's direct-object interface specification.  An
    error will be raised if the module already has an interface specification.
    In other words, it is an error to call this function more than once in a
    module definition.

    This function is provided for convenience. It provides a more convenient
    way to call directlyProvides. For example::

      moduleImplements(I1)

    is equivalent to::

      directlyProvides(sys.modules[__name__], I1)
    """
    frame = sys._getframe(1)
    locals = frame.f_locals

    # Try to make sure we were called from a class def
    if (locals is not frame.f_globals) or ('__name__' not in locals):
        raise TypeError(
            "moduleProvides can only be used from a module definition.")

    if '__provides__' in locals:
        raise TypeError(
            "moduleProvides can only be used once in a module definition.")

    locals["__provides__"] = Provides(ModuleType,
                                      *_normalizeargs(interfaces))

##############################################################################
#
# Declaration querying support

# XXX:  is this a fossil?  Nobody calls it, no unit tests exercise it, no
#       doctests import it, and the package __init__ doesn't import it.
def ObjectSpecification(direct, cls):
    """Provide object specifications

    These combine information for the object and for it's classes.
    """
    return Provides(cls, direct) #pragma NO COVER fossil

def getObjectSpecificationFallback(ob):

    provides = getattr(ob, '__provides__', None)
    if provides is not None:
        if isinstance(provides, SpecificationBase):
            return provides

    try:
        cls = ob.__class__
    except AttributeError:
        # We can't get the class, so just consider provides
        return _empty

    return implementedBy(cls)

getObjectSpecification = getObjectSpecificationFallback

def providedByFallback(ob):

    # Here we have either a special object, an old-style declaration
    # or a descriptor

    # Try to get __providedBy__
    try:
        r = ob.__providedBy__
    except AttributeError:
        # Not set yet. Fall back to lower-level thing that computes it
        return getObjectSpecification(ob)

    try:
        # We might have gotten a descriptor from an instance of a
        # class (like an ExtensionClass) that doesn't support
        # descriptors.  We'll make sure we got one by trying to get
        # the only attribute, which all specs have.
        r.extends

    except AttributeError:

        # The object's class doesn't understand descriptors.
        # Sigh. We need to get an object descriptor, but we have to be
        # careful.  We want to use the instance's __provides__, if
        # there is one, but only if it didn't come from the class.

        try:
            r = ob.__provides__
        except AttributeError:
            # No __provides__, so just fall back to implementedBy
            return implementedBy(ob.__class__)

        # We need to make sure we got the __provides__ from the
        # instance. We'll do this by making sure we don't get the same
        # thing from the class:

        try:
            cp = ob.__class__.__provides__
        except AttributeError:
            # The ob doesn't have a class or the class has no
            # provides, assume we're done:
            return r

        if r is cp:
            # Oops, we got the provides from the class. This means
            # the object doesn't have it's own. We should use implementedBy
            return implementedBy(ob.__class__)

    return r
providedBy = providedByFallback

class ObjectSpecificationDescriptorFallback(object):
    """Implement the `__providedBy__` attribute

    The `__providedBy__` attribute computes the interfaces peovided by
    an object.
    """

    def __get__(self, inst, cls):
        """Get an object specification for an object
        """
        if inst is None:
            return getObjectSpecification(cls)

        provides = getattr(inst, '__provides__', None)
        if provides is not None:
            return provides

        return implementedBy(cls)

ObjectSpecificationDescriptor = ObjectSpecificationDescriptorFallback

##############################################################################

def _normalizeargs(sequence, output = None):
    """Normalize declaration arguments

    Normalization arguments might contain Declarions, tuples, or single
    interfaces.

    Anything but individial interfaces or implements specs will be expanded.
    """
    if output is None:
        output = []

    cls = sequence.__class__
    if InterfaceClass in cls.__mro__ or Implements in cls.__mro__:
        output.append(sequence)
    else:
        for v in sequence:
            _normalizeargs(v, output)

    return output

_empty = Declaration()

try:
    import _zope_interface_coptimizations
except ImportError: #pragma NO COVER
    pass
else: #pragma NO COVER PyPy
    from _zope_interface_coptimizations import implementedBy
    from _zope_interface_coptimizations import providedBy
    from _zope_interface_coptimizations import getObjectSpecification
    from _zope_interface_coptimizations import ObjectSpecificationDescriptor

objectSpecificationDescriptor = ObjectSpecificationDescriptor()

##############################################################################
#
# Copyright (c) 2001, 2002 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Interface object implementation
"""
from __future__ import generators

import sys
from types import MethodType
from types import FunctionType
import warnings
import weakref

from zope.interface.exceptions import Invalid
from zope.interface.ro import ro


CO_VARARGS = 4
CO_VARKEYWORDS = 8
TAGGED_DATA = '__interface_tagged_values__'

_decorator_non_return = object()

def invariant(call):
    f_locals = sys._getframe(1).f_locals
    tags = f_locals.setdefault(TAGGED_DATA, {})
    invariants = tags.setdefault('invariants', [])
    invariants.append(call)
    return _decorator_non_return


def taggedValue(key, value):
    """Attaches a tagged value to an interface at definition time."""
    f_locals = sys._getframe(1).f_locals
    tagged_values = f_locals.setdefault(TAGGED_DATA, {})
    tagged_values[key] = value
    return _decorator_non_return


class Element(object):

    # We can't say this yet because we don't have enough
    # infrastructure in place.
    #
    #implements(IElement)

    def __init__(self, __name__, __doc__=''):
        """Create an 'attribute' description
        """
        if not __doc__ and __name__.find(' ') >= 0:
            __doc__ = __name__
            __name__ = None

        self.__name__=__name__
        self.__doc__=__doc__
        self.__tagged_values = {}

    def getName(self):
        """ Returns the name of the object. """
        return self.__name__

    def getDoc(self):
        """ Returns the documentation for the object. """
        return self.__doc__

    def getTaggedValue(self, tag):
        """ Returns the value associated with 'tag'. """
        return self.__tagged_values[tag]

    def queryTaggedValue(self, tag, default=None):
        """ Returns the value associated with 'tag'. """
        return self.__tagged_values.get(tag, default)

    def getTaggedValueTags(self):
        """ Returns a list of all tags. """
        return self.__tagged_values.keys()

    def setTaggedValue(self, tag, value):
        """ Associates 'value' with 'key'. """
        self.__tagged_values[tag] = value

class SpecificationBasePy(object):

    def providedBy(self, ob):
        """Is the interface implemented by an object
        """
        spec = providedBy(ob)
        return self in spec._implied

    def implementedBy(self, cls):
        """Test whether the specification is implemented by a class or factory.

        Raise TypeError if argument is neither a class nor a callable.
        """
        spec = implementedBy(cls)
        return self in spec._implied

    def isOrExtends(self, interface):
        """Is the interface the same as or extend the given interface
        """
        return interface in self._implied

    __call__ = isOrExtends

SpecificationBase = SpecificationBasePy
try:
    from _zope_interface_coptimizations import SpecificationBase
except ImportError: #pragma NO COVER
    pass

_marker = object()
class InterfaceBasePy(object):
    """Base class that wants to be replaced with a C base :)
    """

    def __call__(self, obj, alternate=_marker):
        """Adapt an object to the interface
        """
        conform = getattr(obj, '__conform__', None)
        if conform is not None:
            adapter = self._call_conform(conform)
            if adapter is not None:
                return adapter

        adapter = self.__adapt__(obj)

        if adapter is not None:
            return adapter
        elif alternate is not _marker:
            return alternate
        else:
            raise TypeError("Could not adapt", obj, self)

    def __adapt__(self, obj):
        """Adapt an object to the reciever
        """
        if self.providedBy(obj):
            return obj

        for hook in adapter_hooks:
            adapter = hook(self, obj)
            if adapter is not None:
                return adapter


InterfaceBase = InterfaceBasePy
try:
    from _zope_interface_coptimizations import InterfaceBase
except ImportError: #pragma NO COVER
    pass


adapter_hooks = []
try:
    from _zope_interface_coptimizations import adapter_hooks
except ImportError: #pragma NO COVER
    pass


class Specification(SpecificationBase):
    """Specifications

    An interface specification is used to track interface declarations
    and component registrations.

    This class is a base class for both interfaces themselves and for
    interface specifications (declarations).

    Specifications are mutable.  If you reassign their bases, their
    relations with other specifications are adjusted accordingly.
    """

    # Copy some base class methods for speed
    isOrExtends = SpecificationBase.isOrExtends
    providedBy = SpecificationBase.providedBy

    def __init__(self, bases=()):
        self._implied = {}
        self.dependents = weakref.WeakKeyDictionary()
        self.__bases__ = tuple(bases)

    def subscribe(self, dependent):
        self.dependents[dependent] = self.dependents.get(dependent, 0) + 1

    def unsubscribe(self, dependent):
        n = self.dependents.get(dependent, 0) - 1
        if not n:
            del self.dependents[dependent]
        elif n > 0:
            self.dependents[dependent] = n
        else:
            raise KeyError(dependent)

    def __setBases(self, bases):
        # Register ourselves as a dependent of our old bases
        for b in self.__bases__:
            b.unsubscribe(self)

        # Register ourselves as a dependent of our bases
        self.__dict__['__bases__'] = bases
        for b in bases:
            b.subscribe(self)

        self.changed(self)

    __bases__ = property(

        lambda self: self.__dict__.get('__bases__', ()),
        __setBases,
        )

    def changed(self, originally_changed):
        """We, or something we depend on, have changed
        """
        try:
            del self._v_attrs
        except AttributeError:
            pass

        implied = self._implied
        implied.clear()

        ancestors = ro(self)

        try:
            if Interface not in ancestors:
                ancestors.append(Interface)
        except NameError:
            pass # defining Interface itself

        self.__sro__ = tuple(ancestors)
        self.__iro__ = tuple([ancestor for ancestor in ancestors
                              if isinstance(ancestor, InterfaceClass)
                              ])

        for ancestor in ancestors:
            # We directly imply our ancestors:
            implied[ancestor] = ()

        # Now, advise our dependents of change:
        for dependent in tuple(self.dependents.keys()):
            dependent.changed(originally_changed)


    def interfaces(self):
        """Return an iterator for the interfaces in the specification.
        """
        seen = {}
        for base in self.__bases__:
            for interface in base.interfaces():
                if interface not in seen:
                    seen[interface] = 1
                    yield interface


    def extends(self, interface, strict=True):
        """Does the specification extend the given interface?

        Test whether an interface in the specification extends the
        given interface
        """
        return ((interface in self._implied)
                and
                ((not strict) or (self != interface))
                )

    def weakref(self, callback=None):
        return weakref.ref(self, callback)

    def get(self, name, default=None):
        """Query for an attribute description
        """
        try:
            attrs = self._v_attrs
        except AttributeError:
            attrs = self._v_attrs = {}
        attr = attrs.get(name)
        if attr is None:
            for iface in self.__iro__:
                attr = iface.direct(name)
                if attr is not None:
                    attrs[name] = attr
                    break

        if attr is None:
            return default
        else:
            return attr

class InterfaceClass(Element, InterfaceBase, Specification):
    """Prototype (scarecrow) Interfaces Implementation."""

    # We can't say this yet because we don't have enough
    # infrastructure in place.
    #
    #implements(IInterface)

    def __init__(self, name, bases=(), attrs=None, __doc__=None,
                 __module__=None):

        if attrs is None:
            attrs = {}

        if __module__ is None:
            __module__ = attrs.get('__module__')
            if isinstance(__module__, str):
                del attrs['__module__']
            else:
                try:
                    # Figure out what module defined the interface.
                    # This is how cPython figures out the module of
                    # a class, but of course it does it in C. :-/
                    __module__ = sys._getframe(1).f_globals['__name__']
                except (AttributeError, KeyError): #pragma NO COVERAGE
                    pass

        self.__module__ = __module__

        d = attrs.get('__doc__')
        if d is not None:
            if not isinstance(d, Attribute):
                if __doc__ is None:
                    __doc__ = d
                del attrs['__doc__']

        if __doc__ is None:
            __doc__ = ''

        Element.__init__(self, name, __doc__)

        tagged_data = attrs.pop(TAGGED_DATA, None)
        if tagged_data is not None:
            for key, val in tagged_data.items():
                self.setTaggedValue(key, val)

        for base in bases:
            if not isinstance(base, InterfaceClass):
                raise TypeError('Expected base interfaces')

        Specification.__init__(self, bases)

        # Make sure that all recorded attributes (and methods) are of type
        # `Attribute` and `Method`
        for name, attr in list(attrs.items()):
            if name in ('__locals__', '__qualname__'):
                # __locals__: Python 3 sometimes adds this.
                # __qualname__: PEP 3155 (Python 3.3+)
                del attrs[name]
                continue
            if isinstance(attr, Attribute):
                attr.interface = self
                if not attr.__name__:
                    attr.__name__ = name
            elif isinstance(attr, FunctionType):
                attrs[name] = fromFunction(attr, self, name=name)
            elif attr is _decorator_non_return:
                del attrs[name]
            else:
                raise InvalidInterface("Concrete attribute, " + name)

        self.__attrs = attrs

        self.__identifier__ = "%s.%s" % (self.__module__, self.__name__)

    def interfaces(self):
        """Return an iterator for the interfaces in the specification.
        """
        yield self

    def getBases(self):
        return self.__bases__

    def isEqualOrExtendedBy(self, other):
        """Same interface or extends?"""
        return self == other or other.extends(self)

    def names(self, all=False):
        """Return the attribute names defined by the interface."""
        if not all:
            return self.__attrs.keys()

        r = self.__attrs.copy()

        for base in self.__bases__:
            r.update(dict.fromkeys(base.names(all)))

        return r.keys()

    def __iter__(self):
        return iter(self.names(all=True))

    def namesAndDescriptions(self, all=False):
        """Return attribute names and descriptions defined by interface."""
        if not all:
            return self.__attrs.items()

        r = {}
        for base in self.__bases__[::-1]:
            r.update(dict(base.namesAndDescriptions(all)))

        r.update(self.__attrs)

        return r.items()

    def getDescriptionFor(self, name):
        """Return the attribute description for the given name."""
        r = self.get(name)
        if r is not None:
            return r

        raise KeyError(name)

    __getitem__ = getDescriptionFor

    def __contains__(self, name):
        return self.get(name) is not None

    def direct(self, name):
        return self.__attrs.get(name)

    def queryDescriptionFor(self, name, default=None):
        return self.get(name, default)

    def validateInvariants(self, obj, errors=None):
        """validate object to defined invariants."""
        for call in self.queryTaggedValue('invariants', []):
            try:
                call(obj)
            except Invalid as e:
                if errors is None:
                    raise
                else:
                    errors.append(e)
        for base in self.__bases__:
            try:
                base.validateInvariants(obj, errors)
            except Invalid:
                if errors is None:
                    raise
        if errors:
            raise Invalid(errors)

    def __repr__(self):  # pragma: no cover
        try:
            return self._v_repr
        except AttributeError:
            name = self.__name__
            m = self.__module__
            if m:
                name = '%s.%s' % (m, name)
            r = "<%s %s>" % (self.__class__.__name__, name)
            self._v_repr = r
            return r

    def _call_conform(self, conform):
        try:
            return conform(self)
        except TypeError: #pragma NO COVER
            # We got a TypeError. It might be an error raised by
            # the __conform__ implementation, or *we* may have
            # made the TypeError by calling an unbound method
            # (object is a class).  In the later case, we behave
            # as though there is no __conform__ method. We can
            # detect this case by checking whether there is more
            # than one traceback object in the traceback chain:
            if sys.exc_info()[2].tb_next is not None:
                # There is more than one entry in the chain, so
                # reraise the error:
                raise
            # This clever trick is from Phillip Eby

        return None #pragma NO COVER

    def __reduce__(self):
        return self.__name__

    def __cmp(self, other):
        # Yes, I did mean to name this __cmp, rather than __cmp__.
        # It is a private method used by __lt__ and __gt__.
        # I don't want to override __eq__ because I want the default
        # __eq__, which is really fast.
        """Make interfaces sortable

        TODO: It would ne nice if:

           More specific interfaces should sort before less specific ones.
           Otherwise, sort on name and module.

           But this is too complicated, and we're going to punt on it
           for now.

        For now, sort on interface and module name.

        None is treated as a pseudo interface that implies the loosest
        contact possible, no contract. For that reason, all interfaces
        sort before None.

        """
        if other is None:
            return -1

        n1 = (getattr(self, '__name__', ''), getattr(self,  '__module__', ''))
        n2 = (getattr(other, '__name__', ''), getattr(other,  '__module__', ''))

        # This spelling works under Python3, which doesn't have cmp().
        return (n1 > n2) - (n1 < n2)

    def __hash__(self):
        d = self.__dict__
        if '__module__' not in d or '__name__' not in d: #pragma NO COVER
            warnings.warn('Hashing uninitialized InterfaceClass instance')
            return 1
        return hash((self.__name__, self.__module__))

    def __eq__(self, other):
        c = self.__cmp(other)
        return c == 0

    def __ne__(self, other):
        c = self.__cmp(other)
        return c != 0

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


Interface = InterfaceClass("Interface", __module__ = 'zope.interface')

class Attribute(Element):
    """Attribute descriptions
    """

    # We can't say this yet because we don't have enough
    # infrastructure in place.
    #
    # implements(IAttribute)

    interface = None


class Method(Attribute):
    """Method interfaces

    The idea here is that you have objects that describe methods.
    This provides an opportunity for rich meta-data.
    """

    # We can't say this yet because we don't have enough
    # infrastructure in place.
    #
    # implements(IMethod)

    positional = required = ()
    _optional = varargs = kwargs = None
    def _get_optional(self):
        if self._optional is None:
            return {}
        return self._optional
    def _set_optional(self, opt):
        self._optional = opt
    def _del_optional(self):
        self._optional = None
    optional = property(_get_optional, _set_optional, _del_optional)

    def __call__(self, *args, **kw):
        raise BrokenImplementation(self.interface, self.__name__)

    def getSignatureInfo(self):
        return {'positional': self.positional,
                'required': self.required,
                'optional': self.optional,
                'varargs': self.varargs,
                'kwargs': self.kwargs,
                }

    def getSignatureString(self):
        sig = []
        for v in self.positional:
            sig.append(v)
            if v in self.optional.keys():
                sig[-1] += "=" + repr(self.optional[v])
        if self.varargs:
            sig.append("*" + self.varargs)
        if self.kwargs:
            sig.append("**" + self.kwargs)

        return "(%s)" % ", ".join(sig)

def fromFunction(func, interface=None, imlevel=0, name=None):
    name = name or func.__name__
    method = Method(name, func.__doc__)
    defaults = getattr(func, '__defaults__', None) or ()
    code = func.__code__
    # Number of positional arguments
    na = code.co_argcount-imlevel
    names = code.co_varnames[imlevel:]
    opt = {}
    # Number of required arguments
    nr = na-len(defaults)
    if nr < 0:
        defaults=defaults[-nr:]
        nr = 0

    # Determine the optional arguments.
    opt.update(dict(zip(names[nr:], defaults)))

    method.positional = names[:na]
    method.required = names[:nr]
    method.optional = opt

    argno = na

    # Determine the function's variable argument's name (i.e. *args)
    if code.co_flags & CO_VARARGS:
        method.varargs = names[argno]
        argno = argno + 1
    else:
        method.varargs = None

    # Determine the function's keyword argument's name (i.e. **kw)
    if code.co_flags & CO_VARKEYWORDS:
        method.kwargs = names[argno]
    else:
        method.kwargs = None

    method.interface = interface

    for key, value in func.__dict__.items():
        method.setTaggedValue(key, value)

    return method


def fromMethod(meth, interface=None, name=None):
    if isinstance(meth, MethodType):
        func = meth.__func__
    else:
        func = meth
    return fromFunction(func, interface, imlevel=1, name=name)


# Now we can create the interesting interfaces and wire them up:
def _wire():
    from zope.interface.declarations import classImplements

    from zope.interface.interfaces import IAttribute
    classImplements(Attribute, IAttribute)

    from zope.interface.interfaces import IMethod
    classImplements(Method, IMethod)

    from zope.interface.interfaces import IInterface
    classImplements(InterfaceClass, IInterface)

    from zope.interface.interfaces import ISpecification
    classImplements(Specification, ISpecification)

# We import this here to deal with module dependencies.
from zope.interface.declarations import implementedBy
from zope.interface.declarations import providedBy
from zope.interface.exceptions import InvalidInterface
from zope.interface.exceptions import BrokenImplementation

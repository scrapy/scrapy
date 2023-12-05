# -*- test-case-name: twisted.spread.test.test_jelly -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
S-expression-based persistence of python objects.

It does something very much like L{Pickle<pickle>}; however, pickle's main goal
seems to be efficiency (both in space and time); jelly's main goals are
security, human readability, and portability to other environments.

This is how Jelly converts various objects to s-expressions.

Boolean::
    True --> ['boolean', 'true']

Integer::
    1 --> 1

List::
    [1, 2] --> ['list', 1, 2]

String::
    \"hello\" --> \"hello\"

Float::
    2.3 --> 2.3

Dictionary::
    {'a': 1, 'b': 'c'} --> ['dictionary', ['b', 'c'], ['a', 1]]

Module::
    UserString --> ['module', 'UserString']

Class::
    UserString.UserString --> ['class', ['module', 'UserString'], 'UserString']

Function::
    string.join --> ['function', 'join', ['module', 'string']]

Instance: s is an instance of UserString.UserString, with a __dict__
{'data': 'hello'}::
    [\"UserString.UserString\", ['dictionary', ['data', 'hello']]]

Class Method: UserString.UserString.center::
    ['method', 'center', ['None'], ['class', ['module', 'UserString'],
     'UserString']]

Instance Method: s.center, where s is an instance of UserString.UserString::
    ['method', 'center', ['instance', ['reference', 1, ['class',
    ['module', 'UserString'], 'UserString']], ['dictionary', ['data', 'd']]],
    ['dereference', 1]]

The Python 2.x C{sets.Set} and C{sets.ImmutableSet} classes are
serialized to the same thing as the builtin C{set} and C{frozenset}
classes.  (This is only relevant if you are communicating with a
version of jelly running on an older version of Python.)

@author: Glyph Lefkowitz

"""

import copy
import datetime
import decimal

# System Imports
import types
import warnings
from functools import reduce

from zope.interface import implementer

from incremental import Version

from twisted.persisted.crefutil import (
    NotKnown,
    _Container,
    _Dereference,
    _DictKeyAndValue,
    _InstanceMethod,
    _Tuple,
)

# Twisted Imports
from twisted.python.compat import nativeString
from twisted.python.deprecate import deprecatedModuleAttribute
from twisted.python.reflect import namedAny, namedObject, qual
from twisted.spread.interfaces import IJellyable, IUnjellyable

DictTypes = (dict,)

None_atom = b"None"  # N
# code
class_atom = b"class"  # c
module_atom = b"module"  # m
function_atom = b"function"  # f

# references
dereference_atom = b"dereference"  # D
persistent_atom = b"persistent"  # p
reference_atom = b"reference"  # r

# mutable collections
dictionary_atom = b"dictionary"  # d
list_atom = b"list"  # l
set_atom = b"set"

# immutable collections
#   (assignment to __dict__ and __class__ still might go away!)
tuple_atom = b"tuple"  # t
instance_atom = b"instance"  # i
frozenset_atom = b"frozenset"


deprecatedModuleAttribute(
    Version("Twisted", 15, 0, 0),
    "instance_atom is unused within Twisted.",
    "twisted.spread.jelly",
    "instance_atom",
)

# errors
unpersistable_atom = b"unpersistable"  # u
unjellyableRegistry = {}
unjellyableFactoryRegistry = {}


def _createBlank(cls):
    """
    Given an object, if that object is a type, return a new, blank instance
    of that type which has not had C{__init__} called on it.  If the object
    is not a type, return L{None}.

    @param cls: The type (or class) to create an instance of.
    @type cls: L{type} or something else that cannot be
        instantiated.

    @return: a new blank instance or L{None} if C{cls} is not a class or type.
    """
    if isinstance(cls, type):
        return cls.__new__(cls)


def _newInstance(cls, state):
    """
    Make a new instance of a class without calling its __init__ method.

    @param state: A C{dict} used to update C{inst.__dict__} either directly or
        via C{__setstate__}, if available.

    @return: A new instance of C{cls}.
    """
    instance = _createBlank(cls)

    def defaultSetter(state):
        instance.__dict__ = state

    setter = getattr(instance, "__setstate__", defaultSetter)
    setter(state)
    return instance


def _maybeClass(classnamep):
    isObject = isinstance(classnamep, type)

    if isObject:
        classnamep = qual(classnamep)

    if not isinstance(classnamep, bytes):
        classnamep = classnamep.encode("utf-8")

    return classnamep


def setUnjellyableForClass(classname, unjellyable):
    """
    Set which local class will represent a remote type.

    If you have written a Copyable class that you expect your client to be
    receiving, write a local "copy" class to represent it, then call::

        jellier.setUnjellyableForClass('module.package.Class', MyCopier).

    Call this at the module level immediately after its class
    definition. MyCopier should be a subclass of RemoteCopy.

    The classname may be a special tag returned by
    'Copyable.getTypeToCopyFor' rather than an actual classname.

    This call is also for cached classes, since there will be no
    overlap.  The rules are the same.
    """

    global unjellyableRegistry
    classname = _maybeClass(classname)
    unjellyableRegistry[classname] = unjellyable
    globalSecurity.allowTypes(classname)


def setUnjellyableFactoryForClass(classname, copyFactory):
    """
    Set the factory to construct a remote instance of a type::

      jellier.setUnjellyableFactoryForClass('module.package.Class', MyFactory)

    Call this at the module level immediately after its class definition.
    C{copyFactory} should return an instance or subclass of
    L{RemoteCopy<pb.RemoteCopy>}.

    Similar to L{setUnjellyableForClass} except it uses a factory instead
    of creating an instance.
    """

    global unjellyableFactoryRegistry
    classname = _maybeClass(classname)
    unjellyableFactoryRegistry[classname] = copyFactory
    globalSecurity.allowTypes(classname)


def setUnjellyableForClassTree(module, baseClass, prefix=None):
    """
    Set all classes in a module derived from C{baseClass} as copiers for
    a corresponding remote class.

    When you have a hierarchy of Copyable (or Cacheable) classes on one
    side, and a mirror structure of Copied (or RemoteCache) classes on the
    other, use this to setUnjellyableForClass all your Copieds for the
    Copyables.

    Each copyTag (the \"classname\" argument to getTypeToCopyFor, and
    what the Copyable's getTypeToCopyFor returns) is formed from
    adding a prefix to the Copied's class name.  The prefix defaults
    to module.__name__.  If you wish the copy tag to consist of solely
    the classname, pass the empty string \'\'.

    @param module: a module object from which to pull the Copied classes.
        (passing sys.modules[__name__] might be useful)

    @param baseClass: the base class from which all your Copied classes derive.

    @param prefix: the string prefixed to classnames to form the
        unjellyableRegistry.
    """
    if prefix is None:
        prefix = module.__name__

    if prefix:
        prefix = "%s." % prefix

    for name in dir(module):
        loaded = getattr(module, name)
        try:
            yes = issubclass(loaded, baseClass)
        except TypeError:
            "It's not a class."
        else:
            if yes:
                setUnjellyableForClass(f"{prefix}{name}", loaded)


def getInstanceState(inst, jellier):
    """
    Utility method to default to 'normal' state rules in serialization.
    """
    if hasattr(inst, "__getstate__"):
        state = inst.__getstate__()
    else:
        state = inst.__dict__
    sxp = jellier.prepare(inst)
    sxp.extend([qual(inst.__class__).encode("utf-8"), jellier.jelly(state)])
    return jellier.preserve(inst, sxp)


def setInstanceState(inst, unjellier, jellyList):
    """
    Utility method to default to 'normal' state rules in unserialization.
    """
    state = unjellier.unjelly(jellyList[1])
    if hasattr(inst, "__setstate__"):
        inst.__setstate__(state)
    else:
        inst.__dict__ = state
    return inst


class Unpersistable:
    """
    This is an instance of a class that comes back when something couldn't be
    unpersisted.
    """

    def __init__(self, reason):
        """
        Initialize an unpersistable object with a descriptive C{reason} string.
        """
        self.reason = reason

    def __repr__(self) -> str:
        return "Unpersistable(%s)" % repr(self.reason)


@implementer(IJellyable)
class Jellyable:
    """
    Inherit from me to Jelly yourself directly with the `getStateFor'
    convenience method.
    """

    def getStateFor(self, jellier):
        return self.__dict__

    def jellyFor(self, jellier):
        """
        @see: L{twisted.spread.interfaces.IJellyable.jellyFor}
        """
        sxp = jellier.prepare(self)
        sxp.extend(
            [
                qual(self.__class__).encode("utf-8"),
                jellier.jelly(self.getStateFor(jellier)),
            ]
        )
        return jellier.preserve(self, sxp)


@implementer(IUnjellyable)
class Unjellyable:
    """
    Inherit from me to Unjelly yourself directly with the
    C{setStateFor} convenience method.
    """

    def setStateFor(self, unjellier, state):
        self.__dict__ = state

    def unjellyFor(self, unjellier, jellyList):
        """
        Perform the inverse operation of L{Jellyable.jellyFor}.

        @see: L{twisted.spread.interfaces.IUnjellyable.unjellyFor}
        """
        state = unjellier.unjelly(jellyList[1])
        self.setStateFor(unjellier, state)
        return self


class _Jellier:
    """
    (Internal) This class manages state for a call to jelly()
    """

    def __init__(self, taster, persistentStore, invoker):
        """
        Initialize.
        """
        self.taster = taster
        # `preserved' is a dict of previously seen instances.
        self.preserved = {}
        # `cooked' is a dict of previously backreferenced instances to their
        # `ref' lists.
        self.cooked = {}
        self.cooker = {}
        self._ref_id = 1
        self.persistentStore = persistentStore
        self.invoker = invoker

    def _cook(self, object):
        """
        (internal) Backreference an object.

        Notes on this method for the hapless future maintainer: If I've already
        gone through the prepare/preserve cycle on the specified object (it is
        being referenced after the serializer is \"done with\" it, e.g. this
        reference is NOT circular), the copy-in-place of aList is relevant,
        since the list being modified is the actual, pre-existing jelly
        expression that was returned for that object. If not, it's technically
        superfluous, since the value in self.preserved didn't need to be set,
        but the invariant that self.preserved[id(object)] is a list is
        convenient because that means we don't have to test and create it or
        not create it here, creating fewer code-paths.  that's why
        self.preserved is always set to a list.

        Sorry that this code is so hard to follow, but Python objects are
        tricky to persist correctly. -glyph
        """
        aList = self.preserved[id(object)]
        newList = copy.copy(aList)
        # make a new reference ID
        refid = self._ref_id
        self._ref_id = self._ref_id + 1
        # replace the old list in-place, so that we don't have to track the
        # previous reference to it.
        aList[:] = [reference_atom, refid, newList]
        self.cooked[id(object)] = [dereference_atom, refid]
        return aList

    def prepare(self, object):
        """
        (internal) Create a list for persisting an object to.  This will allow
        backreferences to be made internal to the object. (circular
        references).

        The reason this needs to happen is that we don't generate an ID for
        every object, so we won't necessarily know which ID the object will
        have in the future.  When it is 'cooked' ( see _cook ), it will be
        assigned an ID, and the temporary placeholder list created here will be
        modified in-place to create an expression that gives this object an ID:
        [reference id# [object-jelly]].
        """

        # create a placeholder list to be preserved
        self.preserved[id(object)] = []
        # keep a reference to this object around, so it doesn't disappear!
        # (This isn't always necessary, but for cases where the objects are
        # dynamically generated by __getstate__ or getStateToCopyFor calls, it
        # is; id() will return the same value for a different object if it gets
        # garbage collected.  This may be optimized later.)
        self.cooker[id(object)] = object
        return []

    def preserve(self, object, sexp):
        """
        (internal) Mark an object's persistent list for later referral.
        """
        # if I've been cooked in the meanwhile,
        if id(object) in self.cooked:
            # replace the placeholder empty list with the real one
            self.preserved[id(object)][2] = sexp
            # but give this one back.
            sexp = self.preserved[id(object)]
        else:
            self.preserved[id(object)] = sexp
        return sexp

    def _checkMutable(self, obj):
        objId = id(obj)
        if objId in self.cooked:
            return self.cooked[objId]
        if objId in self.preserved:
            self._cook(obj)
            return self.cooked[objId]

    def jelly(self, obj):
        if isinstance(obj, Jellyable):
            preRef = self._checkMutable(obj)
            if preRef:
                return preRef
            return obj.jellyFor(self)
        objType = type(obj)
        if self.taster.isTypeAllowed(qual(objType).encode("utf-8")):
            # "Immutable" Types
            if objType in (bytes, int, float):
                return obj
            elif isinstance(obj, types.MethodType):
                aSelf = obj.__self__
                aFunc = obj.__func__
                aClass = aSelf.__class__
                return [
                    b"method",
                    aFunc.__name__,
                    self.jelly(aSelf),
                    self.jelly(aClass),
                ]
            elif objType is str:
                return [b"unicode", obj.encode("UTF-8")]
            elif isinstance(obj, type(None)):
                return [b"None"]
            elif isinstance(obj, types.FunctionType):
                return [b"function", obj.__module__ + "." + obj.__qualname__]
            elif isinstance(obj, types.ModuleType):
                return [b"module", obj.__name__]
            elif objType is bool:
                return [b"boolean", obj and b"true" or b"false"]
            elif objType is datetime.datetime:
                if obj.tzinfo:
                    raise NotImplementedError(
                        "Currently can't jelly datetime objects with tzinfo"
                    )
                return [
                    b"datetime",
                    " ".join(
                        [
                            str(x)
                            for x in (
                                obj.year,
                                obj.month,
                                obj.day,
                                obj.hour,
                                obj.minute,
                                obj.second,
                                obj.microsecond,
                            )
                        ]
                    ).encode("utf-8"),
                ]
            elif objType is datetime.time:
                if obj.tzinfo:
                    raise NotImplementedError(
                        "Currently can't jelly datetime objects with tzinfo"
                    )
                return [
                    b"time",
                    " ".join(
                        [
                            str(x)
                            for x in (obj.hour, obj.minute, obj.second, obj.microsecond)
                        ]
                    ).encode("utf-8"),
                ]
            elif objType is datetime.date:
                return [
                    b"date",
                    " ".join([str(x) for x in (obj.year, obj.month, obj.day)]).encode(
                        "utf-8"
                    ),
                ]
            elif objType is datetime.timedelta:
                return [
                    b"timedelta",
                    " ".join(
                        [str(x) for x in (obj.days, obj.seconds, obj.microseconds)]
                    ).encode("utf-8"),
                ]
            elif issubclass(objType, type):
                return [b"class", qual(obj).encode("utf-8")]
            elif objType is decimal.Decimal:
                return self.jelly_decimal(obj)
            else:
                preRef = self._checkMutable(obj)
                if preRef:
                    return preRef
                # "Mutable" Types
                sxp = self.prepare(obj)
                if objType is list:
                    sxp.extend(self._jellyIterable(list_atom, obj))
                elif objType is tuple:
                    sxp.extend(self._jellyIterable(tuple_atom, obj))
                elif objType in DictTypes:
                    sxp.append(dictionary_atom)
                    for key, val in obj.items():
                        sxp.append([self.jelly(key), self.jelly(val)])
                elif objType is set:
                    sxp.extend(self._jellyIterable(set_atom, obj))
                elif objType is frozenset:
                    sxp.extend(self._jellyIterable(frozenset_atom, obj))
                else:
                    className = qual(obj.__class__).encode("utf-8")
                    persistent = None
                    if self.persistentStore:
                        persistent = self.persistentStore(obj, self)
                    if persistent is not None:
                        sxp.append(persistent_atom)
                        sxp.append(persistent)
                    elif self.taster.isClassAllowed(obj.__class__):
                        sxp.append(className)
                        if hasattr(obj, "__getstate__"):
                            state = obj.__getstate__()
                        else:
                            state = obj.__dict__
                        sxp.append(self.jelly(state))
                    else:
                        self.unpersistable(
                            "instance of class %s deemed insecure"
                            % qual(obj.__class__),
                            sxp,
                        )
                return self.preserve(obj, sxp)
        else:
            raise InsecureJelly(f"Type not allowed for object: {objType} {obj}")

    def _jellyIterable(self, atom, obj):
        """
        Jelly an iterable object.

        @param atom: the identifier atom of the object.
        @type atom: C{str}

        @param obj: any iterable object.
        @type obj: C{iterable}

        @return: a generator of jellied data.
        @rtype: C{generator}
        """
        yield atom
        for item in obj:
            yield self.jelly(item)

    def jelly_decimal(self, d):
        """
        Jelly a decimal object.

        @param d: a decimal object to serialize.
        @type d: C{decimal.Decimal}

        @return: jelly for the decimal object.
        @rtype: C{list}
        """
        sign, guts, exponent = d.as_tuple()
        value = reduce(lambda left, right: left * 10 + right, guts)
        if sign:
            value = -value
        return [b"decimal", value, exponent]

    def unpersistable(self, reason, sxp=None):
        """
        (internal) Returns an sexp: (unpersistable "reason").  Utility method
        for making note that a particular object could not be serialized.
        """
        if sxp is None:
            sxp = []
        sxp.append(unpersistable_atom)
        if isinstance(reason, str):
            reason = reason.encode("utf-8")
        sxp.append(reason)
        return sxp


class _Unjellier:
    def __init__(self, taster, persistentLoad, invoker):
        self.taster = taster
        self.persistentLoad = persistentLoad
        self.references = {}
        self.postCallbacks = []
        self.invoker = invoker

    def unjellyFull(self, obj):
        o = self.unjelly(obj)
        for m in self.postCallbacks:
            m()
        return o

    def _maybePostUnjelly(self, unjellied):
        """
        If the given object has support for the C{postUnjelly} hook, set it up
        to be called at the end of deserialization.

        @param unjellied: an object that has already been unjellied.

        @return: C{unjellied}
        """
        if hasattr(unjellied, "postUnjelly"):
            self.postCallbacks.append(unjellied.postUnjelly)
        return unjellied

    def unjelly(self, obj):
        if type(obj) is not list:
            return obj
        jelTypeBytes = obj[0]
        if not self.taster.isTypeAllowed(jelTypeBytes):
            raise InsecureJelly(jelTypeBytes)
        regClass = unjellyableRegistry.get(jelTypeBytes)
        if regClass is not None:
            method = getattr(_createBlank(regClass), "unjellyFor", regClass)
            return self._maybePostUnjelly(method(self, obj))
        regFactory = unjellyableFactoryRegistry.get(jelTypeBytes)
        if regFactory is not None:
            return self._maybePostUnjelly(regFactory(self.unjelly(obj[1])))

        jelTypeText = nativeString(jelTypeBytes)
        thunk = getattr(self, "_unjelly_%s" % jelTypeText, None)
        if thunk is not None:
            return thunk(obj[1:])
        else:
            nameSplit = jelTypeText.split(".")
            modName = ".".join(nameSplit[:-1])
            if not self.taster.isModuleAllowed(modName):
                raise InsecureJelly(
                    f"Module {modName} not allowed (in type {jelTypeText})."
                )
            clz = namedObject(jelTypeText)
            if not self.taster.isClassAllowed(clz):
                raise InsecureJelly("Class %s not allowed." % jelTypeText)
            return self._genericUnjelly(clz, obj[1])

    def _genericUnjelly(self, cls, state):
        """
        Unjelly a type for which no specific unjellier is registered, but which
        is nonetheless allowed.

        @param cls: the class of the instance we are unjellying.
        @type cls: L{type}

        @param state: The jellied representation of the object's state; its
            C{__dict__} unless it has a C{__setstate__} that takes something
            else.
        @type state: L{list}

        @return: the new, unjellied instance.
        """
        return self._maybePostUnjelly(_newInstance(cls, self.unjelly(state)))

    def _unjelly_None(self, exp):
        return None

    def _unjelly_unicode(self, exp):
        return str(exp[0], "UTF-8")

    def _unjelly_decimal(self, exp):
        """
        Unjelly decimal objects.
        """
        value = exp[0]
        exponent = exp[1]
        if value < 0:
            sign = 1
        else:
            sign = 0
        guts = decimal.Decimal(value).as_tuple()[1]
        return decimal.Decimal((sign, guts, exponent))

    def _unjelly_boolean(self, exp):
        assert exp[0] in (b"true", b"false")
        return exp[0] == b"true"

    def _unjelly_datetime(self, exp):
        return datetime.datetime(*map(int, exp[0].split()))

    def _unjelly_date(self, exp):
        return datetime.date(*map(int, exp[0].split()))

    def _unjelly_time(self, exp):
        return datetime.time(*map(int, exp[0].split()))

    def _unjelly_timedelta(self, exp):
        days, seconds, microseconds = map(int, exp[0].split())
        return datetime.timedelta(days=days, seconds=seconds, microseconds=microseconds)

    def unjellyInto(self, obj, loc, jel):
        o = self.unjelly(jel)
        if isinstance(o, NotKnown):
            o.addDependant(obj, loc)
        obj[loc] = o
        return o

    def _unjelly_dereference(self, lst):
        refid = lst[0]
        x = self.references.get(refid)
        if x is not None:
            return x
        der = _Dereference(refid)
        self.references[refid] = der
        return der

    def _unjelly_reference(self, lst):
        refid = lst[0]
        exp = lst[1]
        o = self.unjelly(exp)
        ref = self.references.get(refid)
        if ref is None:
            self.references[refid] = o
        elif isinstance(ref, NotKnown):
            ref.resolveDependants(o)
            self.references[refid] = o
        else:
            assert 0, "Multiple references with same ID!"
        return o

    def _unjelly_tuple(self, lst):
        l = list(range(len(lst)))
        finished = 1
        for elem in l:
            if isinstance(self.unjellyInto(l, elem, lst[elem]), NotKnown):
                finished = 0
        if finished:
            return tuple(l)
        else:
            return _Tuple(l)

    def _unjelly_list(self, lst):
        l = list(range(len(lst)))
        for elem in l:
            self.unjellyInto(l, elem, lst[elem])
        return l

    def _unjellySetOrFrozenset(self, lst, containerType):
        """
        Helper method to unjelly set or frozenset.

        @param lst: the content of the set.
        @type lst: C{list}

        @param containerType: the type of C{set} to use.
        """
        l = list(range(len(lst)))
        finished = True
        for elem in l:
            data = self.unjellyInto(l, elem, lst[elem])
            if isinstance(data, NotKnown):
                finished = False
        if not finished:
            return _Container(l, containerType)
        else:
            return containerType(l)

    def _unjelly_set(self, lst):
        """
        Unjelly set using the C{set} builtin.
        """
        return self._unjellySetOrFrozenset(lst, set)

    def _unjelly_frozenset(self, lst):
        """
        Unjelly frozenset using the C{frozenset} builtin.
        """
        return self._unjellySetOrFrozenset(lst, frozenset)

    def _unjelly_dictionary(self, lst):
        d = {}
        for k, v in lst:
            kvd = _DictKeyAndValue(d)
            self.unjellyInto(kvd, 0, k)
            self.unjellyInto(kvd, 1, v)
        return d

    def _unjelly_module(self, rest):
        moduleName = nativeString(rest[0])
        if type(moduleName) != str:
            raise InsecureJelly("Attempted to unjelly a module with a non-string name.")
        if not self.taster.isModuleAllowed(moduleName):
            raise InsecureJelly(f"Attempted to unjelly module named {moduleName!r}")
        mod = __import__(moduleName, {}, {}, "x")
        return mod

    def _unjelly_class(self, rest):
        cname = nativeString(rest[0])
        clist = cname.split(nativeString("."))
        modName = nativeString(".").join(clist[:-1])
        if not self.taster.isModuleAllowed(modName):
            raise InsecureJelly("module %s not allowed" % modName)
        klaus = namedObject(cname)
        objType = type(klaus)
        if objType is not type:
            raise InsecureJelly(
                "class %r unjellied to something that isn't a class: %r"
                % (cname, klaus)
            )
        if not self.taster.isClassAllowed(klaus):
            raise InsecureJelly("class not allowed: %s" % qual(klaus))
        return klaus

    def _unjelly_function(self, rest):
        fname = nativeString(rest[0])
        modSplit = fname.split(nativeString("."))
        modName = nativeString(".").join(modSplit[:-1])
        if not self.taster.isModuleAllowed(modName):
            raise InsecureJelly("Module not allowed: %s" % modName)
        # XXX do I need an isFunctionAllowed?
        function = namedAny(fname)
        return function

    def _unjelly_persistent(self, rest):
        if self.persistentLoad:
            pload = self.persistentLoad(rest[0], self)
            return pload
        else:
            return Unpersistable("Persistent callback not found")

    def _unjelly_instance(self, rest):
        """
        (internal) Unjelly an instance.

        Called to handle the deprecated I{instance} token.

        @param rest: The s-expression representing the instance.

        @return: The unjellied instance.
        """
        warnings.warn_explicit(
            "Unjelly support for the instance atom is deprecated since "
            "Twisted 15.0.0.  Upgrade peer for modern instance support.",
            category=DeprecationWarning,
            filename="",
            lineno=0,
        )

        clz = self.unjelly(rest[0])
        return self._genericUnjelly(clz, rest[1])

    def _unjelly_unpersistable(self, rest):
        return Unpersistable(f"Unpersistable data: {rest[0]}")

    def _unjelly_method(self, rest):
        """
        (internal) Unjelly a method.
        """
        im_name = rest[0]
        im_self = self.unjelly(rest[1])
        im_class = self.unjelly(rest[2])
        if not isinstance(im_class, type):
            raise InsecureJelly("Method found with non-class class.")
        if im_name in im_class.__dict__:
            if im_self is None:
                im = getattr(im_class, im_name)
            elif isinstance(im_self, NotKnown):
                im = _InstanceMethod(im_name, im_self, im_class)
            else:
                im = types.MethodType(
                    im_class.__dict__[im_name], im_self, *([im_class] * (False))
                )
        else:
            raise TypeError("instance method changed")
        return im


#### Published Interface.


class InsecureJelly(Exception):
    """
    This exception will be raised when a jelly is deemed `insecure'; e.g. it
    contains a type, class, or module disallowed by the specified `taster'
    """


class DummySecurityOptions:
    """
    DummySecurityOptions() -> insecure security options
    Dummy security options -- this class will allow anything.
    """

    def isModuleAllowed(self, moduleName):
        """
        DummySecurityOptions.isModuleAllowed(moduleName) -> boolean
        returns 1 if a module by that name is allowed, 0 otherwise
        """
        return 1

    def isClassAllowed(self, klass):
        """
        DummySecurityOptions.isClassAllowed(class) -> boolean
        Assumes the module has already been allowed.  Returns 1 if the given
        class is allowed, 0 otherwise.
        """
        return 1

    def isTypeAllowed(self, typeName):
        """
        DummySecurityOptions.isTypeAllowed(typeName) -> boolean
        Returns 1 if the given type is allowed, 0 otherwise.
        """
        return 1


class SecurityOptions:
    """
    This will by default disallow everything, except for 'none'.
    """

    basicTypes = [
        "dictionary",
        "list",
        "tuple",
        "reference",
        "dereference",
        "unpersistable",
        "persistent",
        "long_int",
        "long",
        "dict",
    ]

    def __init__(self):
        """
        SecurityOptions() initialize.
        """
        # I don't believe any of these types can ever pose a security hazard,
        # except perhaps "reference"...
        self.allowedTypes = {
            b"None": 1,
            b"bool": 1,
            b"boolean": 1,
            b"string": 1,
            b"str": 1,
            b"int": 1,
            b"float": 1,
            b"datetime": 1,
            b"time": 1,
            b"date": 1,
            b"timedelta": 1,
            b"NoneType": 1,
            b"unicode": 1,
            b"decimal": 1,
            b"set": 1,
            b"frozenset": 1,
        }
        self.allowedModules = {}
        self.allowedClasses = {}

    def allowBasicTypes(self):
        """
        Allow all `basic' types.  (Dictionary and list.  Int, string, and float
        are implicitly allowed.)
        """
        self.allowTypes(*self.basicTypes)

    def allowTypes(self, *types):
        """
        SecurityOptions.allowTypes(typeString): Allow a particular type, by its
        name.
        """
        for typ in types:
            if isinstance(typ, str):
                typ = typ.encode("utf-8")
            if not isinstance(typ, bytes):
                typ = qual(typ)
            self.allowedTypes[typ] = 1

    def allowInstancesOf(self, *classes):
        """
        SecurityOptions.allowInstances(klass, klass, ...): allow instances
        of the specified classes

        This will also allow the 'instance', 'class' (renamed 'classobj' in
        Python 2.3), and 'module' types, as well as basic types.
        """
        self.allowBasicTypes()
        self.allowTypes("instance", "class", "classobj", "module")
        for klass in classes:
            self.allowTypes(qual(klass))
            self.allowModules(klass.__module__)
            self.allowedClasses[klass] = 1

    def allowModules(self, *modules):
        """
        SecurityOptions.allowModules(module, module, ...): allow modules by
        name. This will also allow the 'module' type.
        """
        for module in modules:
            if type(module) == types.ModuleType:
                module = module.__name__

            if not isinstance(module, bytes):
                module = module.encode("utf-8")

            self.allowedModules[module] = 1

    def isModuleAllowed(self, moduleName):
        """
        SecurityOptions.isModuleAllowed(moduleName) -> boolean
        returns 1 if a module by that name is allowed, 0 otherwise
        """
        if not isinstance(moduleName, bytes):
            moduleName = moduleName.encode("utf-8")

        return moduleName in self.allowedModules

    def isClassAllowed(self, klass):
        """
        SecurityOptions.isClassAllowed(class) -> boolean
        Assumes the module has already been allowed.  Returns 1 if the given
        class is allowed, 0 otherwise.
        """
        return klass in self.allowedClasses

    def isTypeAllowed(self, typeName):
        """
        SecurityOptions.isTypeAllowed(typeName) -> boolean
        Returns 1 if the given type is allowed, 0 otherwise.
        """
        if not isinstance(typeName, bytes):
            typeName = typeName.encode("utf-8")

        return typeName in self.allowedTypes or b"." in typeName


globalSecurity = SecurityOptions()
globalSecurity.allowBasicTypes()


def jelly(object, taster=DummySecurityOptions(), persistentStore=None, invoker=None):
    """
    Serialize to s-expression.

    Returns a list which is the serialized representation of an object.  An
    optional 'taster' argument takes a SecurityOptions and will mark any
    insecure objects as unpersistable rather than serializing them.
    """
    return _Jellier(taster, persistentStore, invoker).jelly(object)


def unjelly(sexp, taster=DummySecurityOptions(), persistentLoad=None, invoker=None):
    """
    Unserialize from s-expression.

    Takes a list that was the result from a call to jelly() and unserializes
    an arbitrary object from it.  The optional 'taster' argument, an instance
    of SecurityOptions, will cause an InsecureJelly exception to be raised if a
    disallowed type, module, or class attempted to unserialize.
    """
    return _Unjellier(taster, persistentLoad, invoker).unjellyFull(sexp)

# -*- test-case-name: twisted.test.test_persisted -*-

# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
AOT: Abstract Object Trees
The source-code-marshallin'est abstract-object-serializin'est persister
this side of Marmalade!
"""


import copyreg as copy_reg
import re
import types
from tokenize import generate_tokens as tokenize

from twisted.persisted import crefutil
from twisted.python import log, reflect
from twisted.python.compat import _constructMethod

###########################
# Abstract Object Classes #
###########################

# "\0" in a getSource means "insert variable-width indention here".
# see `indentify'.


class Named:
    def __init__(self, name):
        self.name = name


class Class(Named):
    def getSource(self):
        return "Class(%r)" % self.name


class Function(Named):
    def getSource(self):
        return "Function(%r)" % self.name


class Module(Named):
    def getSource(self):
        return "Module(%r)" % self.name


class InstanceMethod:
    def __init__(self, name, klass, inst):
        if not (
            isinstance(inst, Ref)
            or isinstance(inst, Instance)
            or isinstance(inst, Deref)
        ):
            raise TypeError("%s isn't an Instance, Ref, or Deref!" % inst)
        self.name = name
        self.klass = klass
        self.instance = inst

    def getSource(self):
        return "InstanceMethod({!r}, {!r}, \n\0{})".format(
            self.name,
            self.klass,
            prettify(self.instance),
        )


class _NoStateObj:
    pass


NoStateObj = _NoStateObj()

_SIMPLE_BUILTINS = [
    bool,
    bytes,
    str,
    int,
    float,
    complex,
    type(None),
    slice,
    type(Ellipsis),
]


class Instance:
    def __init__(self, className, __stateObj__=NoStateObj, **state):
        if not isinstance(className, str):
            raise TypeError("%s isn't a string!" % className)
        self.klass = className
        if __stateObj__ is not NoStateObj:
            self.state = __stateObj__
            self.stateIsDict = 0
        else:
            self.state = state
            self.stateIsDict = 1

    def getSource(self):
        # XXX make state be foo=bar instead of a dict.
        if self.stateIsDict:
            stateDict = self.state
        elif isinstance(self.state, Ref) and isinstance(self.state.obj, dict):
            stateDict = self.state.obj
        else:
            stateDict = None
        if stateDict is not None:
            try:
                return f"Instance({self.klass!r}, {dictToKW(stateDict)})"
            except NonFormattableDict:
                return f"Instance({self.klass!r}, {prettify(stateDict)})"
        return f"Instance({self.klass!r}, {prettify(self.state)})"


class Ref:
    def __init__(self, *args):
        # blargh, lame.
        if len(args) == 2:
            self.refnum = args[0]
            self.obj = args[1]
        elif not args:
            self.refnum = None
            self.obj = None

    def setRef(self, num):
        if self.refnum:
            raise ValueError(f"Error setting id {num}, I already have {self.refnum}")
        self.refnum = num

    def setObj(self, obj):
        if self.obj:
            raise ValueError(f"Error setting obj {obj}, I already have {self.obj}")
        self.obj = obj

    def getSource(self):
        if self.obj is None:
            raise RuntimeError(
                "Don't try to display me before setting an object on me!"
            )
        if self.refnum:
            return "Ref(%d, \n\0%s)" % (self.refnum, prettify(self.obj))
        return prettify(self.obj)


class Deref:
    def __init__(self, num):
        self.refnum = num

    def getSource(self):
        return "Deref(%d)" % self.refnum

    __repr__ = getSource


class Copyreg:
    def __init__(self, loadfunc, state):
        self.loadfunc = loadfunc
        self.state = state

    def getSource(self):
        return f"Copyreg({self.loadfunc!r}, {prettify(self.state)})"


###############
# Marshalling #
###############


def getSource(ao):
    """Pass me an AO, I'll return a nicely-formatted source representation."""
    return indentify("app = " + prettify(ao))


class NonFormattableDict(Exception):
    """A dictionary was not formattable."""


r = re.compile("[a-zA-Z_][a-zA-Z0-9_]*$")


def dictToKW(d):
    out = []
    items = list(d.items())
    items.sort()
    for k, v in items:
        if not isinstance(k, str):
            raise NonFormattableDict("%r ain't a string" % k)
        if not r.match(k):
            raise NonFormattableDict("%r ain't an identifier" % k)
        out.append(f"\n\0{k}={prettify(v)},")
    return "".join(out)


def prettify(obj):
    if hasattr(obj, "getSource"):
        return obj.getSource()
    else:
        # basic type
        t = type(obj)

        if t in _SIMPLE_BUILTINS:
            return repr(obj)

        elif t is dict:
            out = ["{"]
            for k, v in obj.items():
                out.append(f"\n\0{prettify(k)}: {prettify(v)},")
            out.append(len(obj) and "\n\0}" or "}")
            return "".join(out)

        elif t is list:
            out = ["["]
            for x in obj:
                out.append("\n\0%s," % prettify(x))
            out.append(len(obj) and "\n\0]" or "]")
            return "".join(out)

        elif t is tuple:
            out = ["("]
            for x in obj:
                out.append("\n\0%s," % prettify(x))
            out.append(len(obj) and "\n\0)" or ")")
            return "".join(out)
        else:
            raise TypeError(f"Unsupported type {t} when trying to prettify {obj}.")


def indentify(s):
    out = []
    stack = []
    l = ["", s]
    for (
        tokenType,
        tokenString,
        (startRow, startColumn),
        (endRow, endColumn),
        logicalLine,
    ) in tokenize(l.pop):
        if tokenString in ["[", "(", "{"]:
            stack.append(tokenString)
        elif tokenString in ["]", ")", "}"]:
            stack.pop()
        if tokenString == "\0":
            out.append("  " * len(stack))
        else:
            out.append(tokenString)
    return "".join(out)


###########
# Unjelly #
###########


def unjellyFromAOT(aot):
    """
    Pass me an Abstract Object Tree, and I'll unjelly it for you.
    """
    return AOTUnjellier().unjelly(aot)


def unjellyFromSource(stringOrFile):
    """
    Pass me a string of code or a filename that defines an 'app' variable (in
    terms of Abstract Objects!), and I'll execute it and unjelly the resulting
    AOT for you, returning a newly unpersisted Application object!
    """

    ns = {
        "Instance": Instance,
        "InstanceMethod": InstanceMethod,
        "Class": Class,
        "Function": Function,
        "Module": Module,
        "Ref": Ref,
        "Deref": Deref,
        "Copyreg": Copyreg,
    }

    if hasattr(stringOrFile, "read"):
        source = stringOrFile.read()
    else:
        source = stringOrFile
    code = compile(source, "<source>", "exec")
    eval(code, ns, ns)

    if "app" in ns:
        return unjellyFromAOT(ns["app"])
    else:
        raise ValueError("%s needs to define an 'app', it didn't!" % stringOrFile)


class AOTUnjellier:
    """I handle the unjellying of an Abstract Object Tree.
    See AOTUnjellier.unjellyAO
    """

    def __init__(self):
        self.references = {}
        self.stack = []
        self.afterUnjelly = []

    ##
    # unjelly helpers (copied pretty much directly from (now deleted) marmalade)
    ##
    def unjellyLater(self, node):
        """Unjelly a node, later."""
        d = crefutil._Defer()
        self.unjellyInto(d, 0, node)
        return d

    def unjellyInto(self, obj, loc, ao):
        """Utility method for unjellying one object into another.
        This automates the handling of backreferences.
        """
        o = self.unjellyAO(ao)
        obj[loc] = o
        if isinstance(o, crefutil.NotKnown):
            o.addDependant(obj, loc)
        return o

    def callAfter(self, callable, result):
        if isinstance(result, crefutil.NotKnown):
            listResult = [None]
            result.addDependant(listResult, 1)
        else:
            listResult = [result]
        self.afterUnjelly.append((callable, listResult))

    def unjellyAttribute(self, instance, attrName, ao):
        # XXX this is unused????
        """Utility method for unjellying into instances of attributes.

        Use this rather than unjellyAO unless you like surprising bugs!
        Alternatively, you can use unjellyInto on your instance's __dict__.
        """
        self.unjellyInto(instance.__dict__, attrName, ao)

    def unjellyAO(self, ao):
        """Unjelly an Abstract Object and everything it contains.
        I return the real object.
        """
        self.stack.append(ao)
        t = type(ao)
        if t in _SIMPLE_BUILTINS:
            return ao

        elif t is list:
            l = []
            for x in ao:
                l.append(None)
                self.unjellyInto(l, len(l) - 1, x)
            return l

        elif t is tuple:
            l = []
            tuple_ = tuple
            for x in ao:
                l.append(None)
                if isinstance(self.unjellyInto(l, len(l) - 1, x), crefutil.NotKnown):
                    tuple_ = crefutil._Tuple
            return tuple_(l)

        elif t is dict:
            d = {}
            for k, v in ao.items():
                kvd = crefutil._DictKeyAndValue(d)
                self.unjellyInto(kvd, 0, k)
                self.unjellyInto(kvd, 1, v)
            return d
        else:
            # Abstract Objects
            c = ao.__class__
            if c is Module:
                return reflect.namedModule(ao.name)

            elif c in [Class, Function] or issubclass(c, type):
                return reflect.namedObject(ao.name)

            elif c is InstanceMethod:
                im_name = ao.name
                im_class = reflect.namedObject(ao.klass)
                im_self = self.unjellyAO(ao.instance)
                if im_name in im_class.__dict__:
                    if im_self is None:
                        return getattr(im_class, im_name)
                    elif isinstance(im_self, crefutil.NotKnown):
                        return crefutil._InstanceMethod(im_name, im_self, im_class)
                    else:
                        return _constructMethod(im_class, im_name, im_self)
                else:
                    raise TypeError("instance method changed")

            elif c is Instance:
                klass = reflect.namedObject(ao.klass)
                state = self.unjellyAO(ao.state)
                inst = klass.__new__(klass)
                if hasattr(klass, "__setstate__"):
                    self.callAfter(inst.__setstate__, state)
                else:
                    inst.__dict__ = state
                return inst

            elif c is Ref:
                o = self.unjellyAO(ao.obj)  # THIS IS CHANGING THE REF OMG
                refkey = ao.refnum
                ref = self.references.get(refkey)
                if ref is None:
                    self.references[refkey] = o
                elif isinstance(ref, crefutil.NotKnown):
                    ref.resolveDependants(o)
                    self.references[refkey] = o
                elif refkey is None:
                    # This happens when you're unjellying from an AOT not read from source
                    pass
                else:
                    raise ValueError(
                        "Multiple references with the same ID: %s, %s, %s!"
                        % (ref, refkey, ao)
                    )
                return o

            elif c is Deref:
                num = ao.refnum
                ref = self.references.get(num)
                if ref is None:
                    der = crefutil._Dereference(num)
                    self.references[num] = der
                    return der
                return ref

            elif c is Copyreg:
                loadfunc = reflect.namedObject(ao.loadfunc)
                d = self.unjellyLater(ao.state).addCallback(
                    lambda result, _l: _l(*result), loadfunc
                )
                return d
            else:
                raise TypeError("Unsupported AOT type: %s" % t)

    def unjelly(self, ao):
        try:
            l = [None]
            self.unjellyInto(l, 0, ao)
            for func, v in self.afterUnjelly:
                func(v[0])
            return l[0]
        except BaseException:
            log.msg("Error jellying object! Stacktrace follows::")
            log.msg("\n".join(map(repr, self.stack)))
            raise


#########
# Jelly #
#########


def jellyToAOT(obj):
    """Convert an object to an Abstract Object Tree."""
    return AOTJellier().jelly(obj)


def jellyToSource(obj, file=None):
    """
    Pass me an object and, optionally, a file object.
    I'll convert the object to an AOT either return it (if no file was
    specified) or write it to the file.
    """

    aot = jellyToAOT(obj)
    if file:
        file.write(getSource(aot).encode("utf-8"))
    else:
        return getSource(aot)


def _classOfMethod(methodObject):
    """
    Get the associated class of the given method object.

    @param methodObject: a bound method
    @type methodObject: L{types.MethodType}

    @return: a class
    @rtype: L{type}
    """
    return methodObject.__self__.__class__


def _funcOfMethod(methodObject):
    """
    Get the associated function of the given method object.

    @param methodObject: a bound method
    @type methodObject: L{types.MethodType}

    @return: the function implementing C{methodObject}
    @rtype: L{types.FunctionType}
    """
    return methodObject.__func__


def _selfOfMethod(methodObject):
    """
    Get the object that a bound method is bound to.

    @param methodObject: a bound method
    @type methodObject: L{types.MethodType}

    @return: the C{self} passed to C{methodObject}
    @rtype: L{object}
    """
    return methodObject.__self__


class AOTJellier:
    def __init__(self):
        # dict of {id(obj): (obj, node)}
        self.prepared = {}
        self._ref_id = 0
        self.stack = []

    def prepareForRef(self, aoref, object):
        """I prepare an object for later referencing, by storing its id()
        and its _AORef in a cache."""
        self.prepared[id(object)] = aoref

    def jellyToAO(self, obj):
        """I turn an object into an AOT and return it."""
        objType = type(obj)
        self.stack.append(repr(obj))

        # immutable: We don't care if these have multiple refs!
        if objType in _SIMPLE_BUILTINS:
            retval = obj

        elif issubclass(objType, types.MethodType):
            # TODO: make methods 'prefer' not to jelly the object internally,
            # so that the object will show up where it's referenced first NOT
            # by a method.
            retval = InstanceMethod(
                _funcOfMethod(obj).__name__,
                reflect.qual(_classOfMethod(obj)),
                self.jellyToAO(_selfOfMethod(obj)),
            )

        elif issubclass(objType, types.ModuleType):
            retval = Module(obj.__name__)

        elif issubclass(objType, type):
            retval = Class(reflect.qual(obj))

        elif objType is types.FunctionType:
            retval = Function(reflect.fullFuncName(obj))

        else:  # mutable! gotta watch for refs.

            # Marmalade had the nicety of being able to just stick a 'reference' attribute
            # on any Node object that was referenced, but in AOT, the referenced object
            # is *inside* of a Ref call (Ref(num, obj) instead of
            # <objtype ... reference="1">). The problem is, especially for built-in types,
            # I can't just assign some attribute to them to give them a refnum. So, I have
            # to "wrap" a Ref(..) around them later -- that's why I put *everything* that's
            # mutable inside one. The Ref() class will only print the "Ref(..)" around an
            # object if it has a Reference explicitly attached.

            if id(obj) in self.prepared:
                oldRef = self.prepared[id(obj)]
                if oldRef.refnum:
                    # it's been referenced already
                    key = oldRef.refnum
                else:
                    # it hasn't been referenced yet
                    self._ref_id = self._ref_id + 1
                    key = self._ref_id
                    oldRef.setRef(key)
                return Deref(key)

            retval = Ref()

            def _stateFrom(state):
                retval.setObj(
                    Instance(reflect.qual(obj.__class__), self.jellyToAO(state))
                )

            self.prepareForRef(retval, obj)

            if objType is list:
                retval.setObj([self.jellyToAO(o) for o in obj])  # hah!

            elif objType is tuple:
                retval.setObj(tuple(map(self.jellyToAO, obj)))

            elif objType is dict:
                d = {}
                for k, v in obj.items():
                    d[self.jellyToAO(k)] = self.jellyToAO(v)
                retval.setObj(d)

            elif objType in copy_reg.dispatch_table:
                unpickleFunc, state = copy_reg.dispatch_table[objType](obj)

                retval.setObj(
                    Copyreg(reflect.fullFuncName(unpickleFunc), self.jellyToAO(state))
                )

            elif hasattr(obj, "__getstate__"):
                _stateFrom(obj.__getstate__())
            elif hasattr(obj, "__dict__"):
                _stateFrom(obj.__dict__)
            else:
                raise TypeError("Unsupported type: %s" % objType.__name__)

        del self.stack[-1]
        return retval

    def jelly(self, obj):
        try:
            ao = self.jellyToAO(obj)
            return ao
        except BaseException:
            log.msg("Error jellying object! Stacktrace follows::")
            log.msg("\n".join(self.stack))
            raise

# -*- test-case-name: twisted.test.test_reflect -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Standardized versions of various cool and/or strange things that you can do
with Python's reflection capabilities.
"""


import os
import pickle
import re
import sys
import traceback
import types
import weakref
from collections import deque
from io import IOBase, StringIO
from typing import Type, Union

from twisted.python.compat import nativeString
from twisted.python.deprecate import _fullyQualifiedName as fullyQualifiedName

RegexType = type(re.compile(""))


def prefixedMethodNames(classObj, prefix):
    """
    Given a class object C{classObj}, returns a list of method names that match
    the string C{prefix}.

    @param classObj: A class object from which to collect method names.

    @param prefix: A native string giving a prefix.  Each method with a name
        which begins with this prefix will be returned.
    @type prefix: L{str}

    @return: A list of the names of matching methods of C{classObj} (and base
        classes of C{classObj}).
    @rtype: L{list} of L{str}
    """
    dct = {}
    addMethodNamesToDict(classObj, dct, prefix)
    return list(dct.keys())


def addMethodNamesToDict(classObj, dict, prefix, baseClass=None):
    """
    This goes through C{classObj} (and its bases) and puts method names
    starting with 'prefix' in 'dict' with a value of 1. if baseClass isn't
    None, methods will only be added if classObj is-a baseClass

    If the class in question has the methods 'prefix_methodname' and
    'prefix_methodname2', the resulting dict should look something like:
    {"methodname": 1, "methodname2": 1}.

    @param classObj: A class object from which to collect method names.

    @param dict: A L{dict} which will be updated with the results of the
        accumulation.  Items are added to this dictionary, with method names as
        keys and C{1} as values.
    @type dict: L{dict}

    @param prefix: A native string giving a prefix.  Each method of C{classObj}
        (and base classes of C{classObj}) with a name which begins with this
        prefix will be returned.
    @type prefix: L{str}

    @param baseClass: A class object at which to stop searching upwards for new
        methods.  To collect all method names, do not pass a value for this
        parameter.

    @return: L{None}
    """
    for base in classObj.__bases__:
        addMethodNamesToDict(base, dict, prefix, baseClass)

    if baseClass is None or baseClass in classObj.__bases__:
        for name, method in classObj.__dict__.items():
            optName = name[len(prefix) :]
            if (
                (type(method) is types.FunctionType)
                and (name[: len(prefix)] == prefix)
                and (len(optName))
            ):
                dict[optName] = 1


def prefixedMethods(obj, prefix=""):
    """
    Given an object C{obj}, returns a list of method objects that match the
    string C{prefix}.

    @param obj: An arbitrary object from which to collect methods.

    @param prefix: A native string giving a prefix.  Each method of C{obj} with
        a name which begins with this prefix will be returned.
    @type prefix: L{str}

    @return: A list of the matching method objects.
    @rtype: L{list}
    """
    dct = {}
    accumulateMethods(obj, dct, prefix)
    return list(dct.values())


def accumulateMethods(obj, dict, prefix="", curClass=None):
    """
    Given an object C{obj}, add all methods that begin with C{prefix}.

    @param obj: An arbitrary object to collect methods from.

    @param dict: A L{dict} which will be updated with the results of the
        accumulation.  Items are added to this dictionary, with method names as
        keys and corresponding instance method objects as values.
    @type dict: L{dict}

    @param prefix: A native string giving a prefix.  Each method of C{obj} with
        a name which begins with this prefix will be returned.
    @type prefix: L{str}

    @param curClass: The class in the inheritance hierarchy at which to start
        collecting methods.  Collection proceeds up.  To collect all methods
        from C{obj}, do not pass a value for this parameter.

    @return: L{None}
    """
    if not curClass:
        curClass = obj.__class__
    for base in curClass.__bases__:
        # The implementation of the object class is different on PyPy vs.
        # CPython.  This has the side effect of making accumulateMethods()
        # pick up object methods from all new-style classes -
        # such as __getattribute__, etc.
        # If we ignore 'object' when accumulating methods, we can get
        # consistent behavior on Pypy and CPython.
        if base is not object:
            accumulateMethods(obj, dict, prefix, base)

    for name, method in curClass.__dict__.items():
        optName = name[len(prefix) :]
        if (
            (type(method) is types.FunctionType)
            and (name[: len(prefix)] == prefix)
            and (len(optName))
        ):
            dict[optName] = getattr(obj, name)


def namedModule(name):
    """
    Return a module given its name.
    """
    topLevel = __import__(name)
    packages = name.split(".")[1:]
    m = topLevel
    for p in packages:
        m = getattr(m, p)
    return m


def namedObject(name):
    """
    Get a fully named module-global object.
    """
    classSplit = name.split(".")
    module = namedModule(".".join(classSplit[:-1]))
    return getattr(module, classSplit[-1])


namedClass = namedObject  # backwards compat


def requireModule(name, default=None):
    """
    Try to import a module given its name, returning C{default} value if
    C{ImportError} is raised during import.

    @param name: Module name as it would have been passed to C{import}.
    @type name: C{str}.

    @param default: Value returned in case C{ImportError} is raised while
        importing the module.

    @return: Module or default value.
    """
    try:
        return namedModule(name)
    except ImportError:
        return default


class _NoModuleFound(Exception):
    """
    No module was found because none exists.
    """


class InvalidName(ValueError):
    """
    The given name is not a dot-separated list of Python objects.
    """


class ModuleNotFound(InvalidName):
    """
    The module associated with the given name doesn't exist and it can't be
    imported.
    """


class ObjectNotFound(InvalidName):
    """
    The object associated with the given name doesn't exist and it can't be
    imported.
    """


def _importAndCheckStack(importName):
    """
    Import the given name as a module, then walk the stack to determine whether
    the failure was the module not existing, or some code in the module (for
    example a dependent import) failing.  This can be helpful to determine
    whether any actual application code was run.  For example, to distiguish
    administrative error (entering the wrong module name), from programmer
    error (writing buggy code in a module that fails to import).

    @param importName: The name of the module to import.
    @type importName: C{str}
    @raise Exception: if something bad happens.  This can be any type of
        exception, since nobody knows what loading some arbitrary code might
        do.
    @raise _NoModuleFound: if no module was found.
    """
    try:
        return __import__(importName)
    except ImportError:
        excType, excValue, excTraceback = sys.exc_info()
        while excTraceback:
            execName = excTraceback.tb_frame.f_globals["__name__"]
            if execName == importName:
                raise excValue.with_traceback(excTraceback)
            excTraceback = excTraceback.tb_next
        raise _NoModuleFound()


def namedAny(name):
    """
    Retrieve a Python object by its fully qualified name from the global Python
    module namespace.  The first part of the name, that describes a module,
    will be discovered and imported.  Each subsequent part of the name is
    treated as the name of an attribute of the object specified by all of the
    name which came before it.  For example, the fully-qualified name of this
    object is 'twisted.python.reflect.namedAny'.

    @type name: L{str}
    @param name: The name of the object to return.

    @raise InvalidName: If the name is an empty string, starts or ends with
        a '.', or is otherwise syntactically incorrect.

    @raise ModuleNotFound: If the name is syntactically correct but the
        module it specifies cannot be imported because it does not appear to
        exist.

    @raise ObjectNotFound: If the name is syntactically correct, includes at
        least one '.', but the module it specifies cannot be imported because
        it does not appear to exist.

    @raise AttributeError: If an attribute of an object along the way cannot be
        accessed, or a module along the way is not found.

    @return: the Python object identified by 'name'.
    """
    if not name:
        raise InvalidName("Empty module name")

    names = name.split(".")

    # if the name starts or ends with a '.' or contains '..', the __import__
    # will raise an 'Empty module name' error. This will provide a better error
    # message.
    if "" in names:
        raise InvalidName(
            "name must be a string giving a '.'-separated list of Python "
            "identifiers, not %r" % (name,)
        )

    topLevelPackage = None
    moduleNames = names[:]
    while not topLevelPackage:
        if moduleNames:
            trialname = ".".join(moduleNames)
            try:
                topLevelPackage = _importAndCheckStack(trialname)
            except _NoModuleFound:
                moduleNames.pop()
        else:
            if len(names) == 1:
                raise ModuleNotFound(f"No module named {name!r}")
            else:
                raise ObjectNotFound(f"{name!r} does not name an object")

    obj = topLevelPackage
    for n in names[1:]:
        obj = getattr(obj, n)

    return obj


def filenameToModuleName(fn):
    """
    Convert a name in the filesystem to the name of the Python module it is.

    This is aggressive about getting a module name back from a file; it will
    always return a string.  Aggressive means 'sometimes wrong'; it won't look
    at the Python path or try to do any error checking: don't use this method
    unless you already know that the filename you're talking about is a Python
    module.

    @param fn: A filesystem path to a module or package; C{bytes} on Python 2,
        C{bytes} or C{unicode} on Python 3.

    @return: A hopefully importable module name.
    @rtype: C{str}
    """
    if isinstance(fn, bytes):
        initPy = b"__init__.py"
    else:
        initPy = "__init__.py"
    fullName = os.path.abspath(fn)
    base = os.path.basename(fn)
    if not base:
        # this happens when fn ends with a path separator, just skit it
        base = os.path.basename(fn[:-1])
    modName = nativeString(os.path.splitext(base)[0])
    while 1:
        fullName = os.path.dirname(fullName)
        if os.path.exists(os.path.join(fullName, initPy)):
            modName = "{}.{}".format(
                nativeString(os.path.basename(fullName)),
                nativeString(modName),
            )
        else:
            break
    return modName


def qual(clazz: Type[object]) -> str:
    """
    Return full import path of a class.
    """
    return clazz.__module__ + "." + clazz.__name__


def _determineClass(x):
    try:
        return x.__class__
    except BaseException:
        return type(x)


def _determineClassName(x):
    c = _determineClass(x)
    try:
        return c.__name__
    except BaseException:
        try:
            return str(c)
        except BaseException:
            return "<BROKEN CLASS AT 0x%x>" % id(c)


def _safeFormat(formatter: Union[types.FunctionType, Type[str]], o: object) -> str:
    """
    Helper function for L{safe_repr} and L{safe_str}.

    Called when C{repr} or C{str} fail. Returns a string containing info about
    C{o} and the latest exception.

    @param formatter: C{str} or C{repr}.
    @type formatter: C{type}
    @param o: Any object.

    @rtype: C{str}
    @return: A string containing information about C{o} and the raised
        exception.
    """
    io = StringIO()
    traceback.print_exc(file=io)
    className = _determineClassName(o)
    tbValue = io.getvalue()
    return "<{} instance at 0x{:x} with {} error:\n {}>".format(
        className,
        id(o),
        formatter.__name__,
        tbValue,
    )


def safe_repr(o):
    """
    Returns a string representation of an object, or a string containing a
    traceback, if that object's __repr__ raised an exception.

    @param o: Any object.

    @rtype: C{str}
    """
    try:
        return repr(o)
    except BaseException:
        return _safeFormat(repr, o)


def safe_str(o: object) -> str:
    """
    Returns a string representation of an object, or a string containing a
    traceback, if that object's __str__ raised an exception.

    @param o: Any object.
    """
    if isinstance(o, bytes):
        # If o is bytes and seems to holds a utf-8 encoded string,
        # convert it to str.
        try:
            return o.decode("utf-8")
        except BaseException:
            pass
    try:
        return str(o)
    except BaseException:
        return _safeFormat(str, o)


class QueueMethod:
    """
    I represent a method that doesn't exist yet.
    """

    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    def __call__(self, *args):
        self.calls.append((self.name, args))


def fullFuncName(func):
    qualName = str(pickle.whichmodule(func, func.__name__)) + "." + func.__name__
    if namedObject(qualName) is not func:
        raise Exception(f"Couldn't find {func} as {qualName}.")
    return qualName


def getClass(obj):
    """
    Return the class or type of object 'obj'.
    """
    return type(obj)


def accumulateClassDict(classObj, attr, adict, baseClass=None):
    """
    Accumulate all attributes of a given name in a class hierarchy into a single dictionary.

    Assuming all class attributes of this name are dictionaries.
    If any of the dictionaries being accumulated have the same key, the
    one highest in the class hierarchy wins.
    (XXX: If \"highest\" means \"closest to the starting class\".)

    Ex::

      class Soy:
        properties = {\"taste\": \"bland\"}

      class Plant:
        properties = {\"colour\": \"green\"}

      class Seaweed(Plant):
        pass

      class Lunch(Soy, Seaweed):
        properties = {\"vegan\": 1 }

      dct = {}

      accumulateClassDict(Lunch, \"properties\", dct)

      print(dct)

    {\"taste\": \"bland\", \"colour\": \"green\", \"vegan\": 1}
    """
    for base in classObj.__bases__:
        accumulateClassDict(base, attr, adict)
    if baseClass is None or baseClass in classObj.__bases__:
        adict.update(classObj.__dict__.get(attr, {}))


def accumulateClassList(classObj, attr, listObj, baseClass=None):
    """
    Accumulate all attributes of a given name in a class hierarchy into a single list.

    Assuming all class attributes of this name are lists.
    """
    for base in classObj.__bases__:
        accumulateClassList(base, attr, listObj)
    if baseClass is None or baseClass in classObj.__bases__:
        listObj.extend(classObj.__dict__.get(attr, []))


def isSame(a, b):
    return a is b


def isLike(a, b):
    return a == b


def modgrep(goal):
    return objgrep(sys.modules, goal, isLike, "sys.modules")


def isOfType(start, goal):
    return type(start) is goal


def findInstances(start, t):
    return objgrep(start, t, isOfType)


def objgrep(
    start,
    goal,
    eq=isLike,
    path="",
    paths=None,
    seen=None,
    showUnknowns=0,
    maxDepth=None,
):
    """
    L{objgrep} finds paths between C{start} and C{goal}.

    Starting at the python object C{start}, we will loop over every reachable
    reference, tring to find the python object C{goal} (i.e. every object
    C{candidate} for whom C{eq(candidate, goal)} is truthy), and return a
    L{list} of L{str}, where each L{str} is Python syntax for a path between
    C{start} and C{goal}.

    Since this can be slightly difficult to visualize, here's an example::

        >>> class Holder:
        ...     def __init__(self, x):
        ...         self.x = x
        ...
        >>> start = Holder({"irrelevant": "ignore",
        ...                 "relevant": [7, 1, 3, 5, 7]})
        >>> for path in objgrep(start, 7):
        ...     print("start" + path)
        start.x['relevant'][0]
        start.x['relevant'][4]

    This can be useful, for example, when debugging stateful graphs of objects
    attached to a socket, trying to figure out where a particular connection is
    attached.

    @param start: The object to start looking at.

    @param goal: The object to search for.

    @param eq: A 2-argument predicate which takes an object found by traversing
        references starting at C{start}, as well as C{goal}, and returns a
        boolean.

    @param path: The prefix of the path to include in every return value; empty
        by default.

    @param paths: The result object to append values to; a list of strings.

    @param seen: A dictionary mapping ints (object IDs) to objects already
        seen.

    @param showUnknowns: if true, print a message to C{stdout} when
        encountering objects that C{objgrep} does not know how to traverse.

    @param maxDepth: The maximum number of object references to attempt
        traversing before giving up.  If an integer, limit to that many links,
        if C{None}, unlimited.

    @return: A list of strings representing python object paths starting at
        C{start} and terminating at C{goal}.
    """
    if paths is None:
        paths = []
    if seen is None:
        seen = {}
    if eq(start, goal):
        paths.append(path)
    if id(start) in seen:
        if seen[id(start)] is start:
            return
    if maxDepth is not None:
        if maxDepth == 0:
            return
        maxDepth -= 1
    seen[id(start)] = start
    # Make an alias for those arguments which are passed recursively to
    # objgrep for container objects.
    args = (paths, seen, showUnknowns, maxDepth)
    if isinstance(start, dict):
        for k, v in start.items():
            objgrep(k, goal, eq, path + "{" + repr(v) + "}", *args)
            objgrep(v, goal, eq, path + "[" + repr(k) + "]", *args)
    elif isinstance(start, (list, tuple, deque)):
        for idx, _elem in enumerate(start):
            objgrep(start[idx], goal, eq, path + "[" + str(idx) + "]", *args)
    elif isinstance(start, types.MethodType):
        objgrep(start.__self__, goal, eq, path + ".__self__", *args)
        objgrep(start.__func__, goal, eq, path + ".__func__", *args)
        objgrep(start.__self__.__class__, goal, eq, path + ".__self__.__class__", *args)
    elif hasattr(start, "__dict__"):
        for k, v in start.__dict__.items():
            objgrep(v, goal, eq, path + "." + k, *args)
    elif isinstance(start, weakref.ReferenceType):
        objgrep(start(), goal, eq, path + "()", *args)
    elif isinstance(
        start,
        (
            str,
            int,
            types.FunctionType,
            types.BuiltinMethodType,
            RegexType,
            float,
            type(None),
            IOBase,
        ),
    ) or type(start).__name__ in (
        "wrapper_descriptor",
        "method_descriptor",
        "member_descriptor",
        "getset_descriptor",
    ):
        pass
    elif showUnknowns:
        print("unknown type", type(start), start)
    return paths


__all__ = [
    "InvalidName",
    "ModuleNotFound",
    "ObjectNotFound",
    "QueueMethod",
    "namedModule",
    "namedObject",
    "namedClass",
    "namedAny",
    "requireModule",
    "safe_repr",
    "safe_str",
    "prefixedMethodNames",
    "addMethodNamesToDict",
    "prefixedMethods",
    "accumulateMethods",
    "fullFuncName",
    "qual",
    "getClass",
    "accumulateClassDict",
    "accumulateClassList",
    "isSame",
    "isLike",
    "modgrep",
    "isOfType",
    "findInstances",
    "objgrep",
    "filenameToModuleName",
    "fullyQualifiedName",
]


# This is to be removed when fixing #6986
__all__.remove("objgrep")

# -*- test-case-name: twisted.test.test_rebuild -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
*Real* reloading support for Python.
"""

import linecache

# System Imports
import sys
import time
import types
from imp import reload
from types import ModuleType
from typing import Dict

# Sibling Imports
from twisted.python import log, reflect

lastRebuild = time.time()


class Sensitive:
    """
    A utility mixin that's sensitive to rebuilds.

    This is a mixin for classes (usually those which represent collections of
    callbacks) to make sure that their code is up-to-date before running.
    """

    lastRebuild = lastRebuild

    def needRebuildUpdate(self):
        yn = self.lastRebuild < lastRebuild
        return yn

    def rebuildUpToDate(self):
        self.lastRebuild = time.time()

    def latestVersionOf(self, anObject):
        """
        Get the latest version of an object.

        This can handle just about anything callable; instances, functions,
        methods, and classes.
        """
        t = type(anObject)
        if t == types.FunctionType:
            return latestFunction(anObject)
        elif t == types.MethodType:
            if anObject.__self__ is None:
                return getattr(anObject.im_class, anObject.__name__)
            else:
                return getattr(anObject.__self__, anObject.__name__)
        else:
            log.msg("warning returning anObject!")
            return anObject


_modDictIDMap: Dict[int, ModuleType] = {}


def latestFunction(oldFunc):
    """
    Get the latest version of a function.
    """
    # This may be CPython specific, since I believe jython instantiates a new
    # module upon reload.
    dictID = id(oldFunc.__globals__)
    module = _modDictIDMap.get(dictID)
    if module is None:
        return oldFunc
    return getattr(module, oldFunc.__name__)


def latestClass(oldClass):
    """
    Get the latest version of a class.
    """
    module = reflect.namedModule(oldClass.__module__)
    newClass = getattr(module, oldClass.__name__)
    newBases = [latestClass(base) for base in newClass.__bases__]

    if newClass.__module__ == "builtins":
        # builtin members can't be reloaded sanely
        return newClass

    try:
        # This makes old-style stuff work
        newClass.__bases__ = tuple(newBases)
        return newClass
    except TypeError:
        ctor = type(newClass)
        return ctor(newClass.__name__, tuple(newBases), dict(newClass.__dict__))


class RebuildError(Exception):
    """
    Exception raised when trying to rebuild a class whereas it's not possible.
    """


def updateInstance(self):
    """
    Updates an instance to be current.
    """
    self.__class__ = latestClass(self.__class__)


def __injectedgetattr__(self, name):
    """
    A getattr method to cause a class to be refreshed.
    """
    if name == "__del__":
        raise AttributeError("Without this, Python segfaults.")
    updateInstance(self)
    log.msg(f"(rebuilding stale {reflect.qual(self.__class__)} instance ({name}))")
    result = getattr(self, name)
    return result


def rebuild(module, doLog=1):
    """
    Reload a module and do as much as possible to replace its references.
    """
    global lastRebuild
    lastRebuild = time.time()
    if hasattr(module, "ALLOW_TWISTED_REBUILD"):
        # Is this module allowed to be rebuilt?
        if not module.ALLOW_TWISTED_REBUILD:
            raise RuntimeError("I am not allowed to be rebuilt.")
    if doLog:
        log.msg(f"Rebuilding {str(module.__name__)}...")

    # Safely handle adapter re-registration
    from twisted.python import components

    components.ALLOW_DUPLICATES = True

    d = module.__dict__
    _modDictIDMap[id(d)] = module
    newclasses = {}
    classes = {}
    functions = {}
    values = {}
    if doLog:
        log.msg(f"  (scanning {str(module.__name__)}): ")
    for k, v in d.items():
        if issubclass(type(v), types.FunctionType):
            if v.__globals__ is module.__dict__:
                functions[v] = 1
                if doLog:
                    log.logfile.write("f")
                    log.logfile.flush()
        elif isinstance(v, type):
            if v.__module__ == module.__name__:
                newclasses[v] = 1
                if doLog:
                    log.logfile.write("o")
                    log.logfile.flush()

    values.update(classes)
    values.update(functions)
    fromOldModule = values.__contains__
    newclasses = newclasses.keys()
    classes = classes.keys()
    functions = functions.keys()

    if doLog:
        log.msg("")
        log.msg(f"  (reload   {str(module.__name__)})")

    # Boom.
    reload(module)
    # Make sure that my traceback printing will at least be recent...
    linecache.clearcache()

    if doLog:
        log.msg(f"  (cleaning {str(module.__name__)}): ")

    for clazz in classes:
        if getattr(module, clazz.__name__) is clazz:
            log.msg(f"WARNING: class {reflect.qual(clazz)} not replaced by reload!")
        else:
            if doLog:
                log.logfile.write("x")
                log.logfile.flush()
            clazz.__bases__ = ()
            clazz.__dict__.clear()
            clazz.__getattr__ = __injectedgetattr__
            clazz.__module__ = module.__name__
    if newclasses:
        import gc
    for nclass in newclasses:
        ga = getattr(module, nclass.__name__)
        if ga is nclass:
            log.msg(
                "WARNING: new-class {} not replaced by reload!".format(
                    reflect.qual(nclass)
                )
            )
        else:
            for r in gc.get_referrers(nclass):
                if getattr(r, "__class__", None) is nclass:
                    r.__class__ = ga
    if doLog:
        log.msg("")
        log.msg(f"  (fixing   {str(module.__name__)}): ")
    modcount = 0
    for mk, mod in sys.modules.items():
        modcount = modcount + 1
        if mod == module or mod is None:
            continue

        if not hasattr(mod, "__file__"):
            # It's a builtin module; nothing to replace here.
            continue

        if hasattr(mod, "__bundle__"):
            # PyObjC has a few buggy objects which segfault if you hash() them.
            # It doesn't make sense to try rebuilding extension modules like
            # this anyway, so don't try.
            continue

        changed = 0

        for k, v in mod.__dict__.items():
            try:
                hash(v)
            except Exception:
                continue
            if fromOldModule(v):
                if doLog:
                    log.logfile.write("f")
                    log.logfile.flush()
                nv = latestFunction(v)
                changed = 1
                setattr(mod, k, nv)
        if doLog and not changed and ((modcount % 10) == 0):
            log.logfile.write(".")
            log.logfile.flush()

    components.ALLOW_DUPLICATES = False
    if doLog:
        log.msg("")
        log.msg(f"   Rebuilt {str(module.__name__)}.")
    return module

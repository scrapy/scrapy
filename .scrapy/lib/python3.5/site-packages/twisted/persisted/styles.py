# -*- test-case-name: twisted.test.test_persisted -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Different styles of persisted objects.
"""

from __future__ import division, absolute_import

# System Imports
import types
import pickle
try:
    import copy_reg
except ImportError:
    import copyreg as copy_reg
import copy
import inspect

from twisted.python.compat import _PY3, _PYPY

# Twisted Imports
from twisted.python import log
from twisted.python import reflect

oldModules = {}


try:
    import cPickle
except ImportError:
    cPickle = None

if cPickle is None or cPickle.PicklingError is pickle.PicklingError:
    _UniversalPicklingError = pickle.PicklingError
else:
    class _UniversalPicklingError(pickle.PicklingError,
                                  cPickle.PicklingError):
        """
        A PicklingError catchable by both L{cPickle.PicklingError} and
        L{pickle.PicklingError} handlers.
        """


## First, let's register support for some stuff that really ought to
## be registerable...

def pickleMethod(method):
    'support function for copy_reg to pickle method refs'
    if _PY3:
        return (unpickleMethod, (method.__name__,
                                 method.__self__,
                                 method.__self__.__class__))
    else:
        return (unpickleMethod, (method.im_func.__name__,
                                 method.im_self,
                                 method.im_class))



def _methodFunction(classObject, methodName):
    """
    Retrieve the function object implementing a method name given the class
    it's on and a method name.

    @param classObject: A class to retrieve the method's function from.
    @type classObject: L{type} or L{types.ClassType}

    @param methodName: The name of the method whose function to retrieve.
    @type methodName: native L{str}

    @return: the function object corresponding to the given method name.
    @rtype: L{types.FunctionType}
    """
    methodObject = getattr(classObject, methodName)
    if _PY3:
        return methodObject
    return methodObject.im_func



def unpickleMethod(im_name, im_self, im_class):
    """
    Support function for copy_reg to unpickle method refs.

    @param im_name: The name of the method.
    @type im_name: native L{str}

    @param im_self: The instance that the method was present on.
    @type im_self: L{object}

    @param im_class: The class where the method was declared.
    @type im_class: L{types.ClassType} or L{type} or L{None}
    """
    if im_self is None:
        return getattr(im_class, im_name)
    try:
        methodFunction = _methodFunction(im_class, im_name)
    except AttributeError:
        log.msg("Method", im_name, "not on class", im_class)
        assert im_self is not None, "No recourse: no instance to guess from."
        # Attempt a last-ditch fix before giving up. If classes have changed
        # around since we pickled this method, we may still be able to get it
        # by looking on the instance's current class.
        if im_self.__class__ is im_class:
            raise
        return unpickleMethod(im_name, im_self, im_self.__class__)
    else:
        if _PY3:
            maybeClass = ()
        else:
            maybeClass = tuple([im_class])
        bound = types.MethodType(methodFunction, im_self, *maybeClass)
        return bound



copy_reg.pickle(types.MethodType, pickleMethod, unpickleMethod)

def _pickleFunction(f):
    """
    Reduce, in the sense of L{pickle}'s C{object.__reduce__} special method, a
    function object into its constituent parts.

    @param f: The function to reduce.
    @type f: L{types.FunctionType}

    @return: a 2-tuple of a reference to L{_unpickleFunction} and a tuple of
        its arguments, a 1-tuple of the function's fully qualified name.
    @rtype: 2-tuple of C{callable, native string}
    """
    if f.__name__ == '<lambda>':
        raise _UniversalPicklingError(
            "Cannot pickle lambda function: {}".format(f))
    return (_unpickleFunction,
            tuple([".".join([f.__module__, f.__qualname__])]))



def _unpickleFunction(fullyQualifiedName):
    """
    Convert a function name into a function by importing it.

    This is a synonym for L{twisted.python.reflect.namedAny}, but imported
    locally to avoid circular imports, and also to provide a persistent name
    that can be stored (and deprecated) independently of C{namedAny}.

    @param fullyQualifiedName: The fully qualified name of a function.
    @type fullyQualifiedName: native C{str}

    @return: A function object imported from the given location.
    @rtype: L{types.FunctionType}
    """
    from twisted.python.reflect import namedAny
    return namedAny(fullyQualifiedName)



copy_reg.pickle(types.FunctionType, _pickleFunction, _unpickleFunction)

def pickleModule(module):
    'support function for copy_reg to pickle module refs'
    return unpickleModule, (module.__name__,)

def unpickleModule(name):
    'support function for copy_reg to unpickle module refs'
    if name in oldModules:
        log.msg("Module has moved: %s" % name)
        name = oldModules[name]
        log.msg(name)
    return __import__(name,{},{},'x')


copy_reg.pickle(types.ModuleType,
                pickleModule,
                unpickleModule)



def pickleStringO(stringo):
    """
    Reduce the given cStringO.

    This is only called on Python 2, because the cStringIO module only exists
    on Python 2.

    @param stringo: The string output to pickle.
    @type stringo: L{cStringIO.OutputType}
    """
    'support function for copy_reg to pickle StringIO.OutputTypes'
    return unpickleStringO, (stringo.getvalue(), stringo.tell())



def unpickleStringO(val, sek):
    """
    Convert the output of L{pickleStringO} into an appropriate type for the
    current python version.  This may be called on Python 3 and will convert a
    cStringIO into an L{io.StringIO}.

    @param val: The content of the file.
    @type val: L{bytes}

    @param sek: The seek position of the file.
    @type sek: L{int}

    @return: a file-like object which you can write bytes to.
    @rtype: L{cStringIO.OutputType} on Python 2, L{io.StringIO} on Python 3.
    """
    x = _cStringIO()
    x.write(val)
    x.seek(sek)
    return x



def pickleStringI(stringi):
    """
    Reduce the given cStringI.

    This is only called on Python 2, because the cStringIO module only exists
    on Python 2.

    @param stringi: The string input to pickle.
    @type stringi: L{cStringIO.InputType}

    @return: a 2-tuple of (C{unpickleStringI}, (bytes, pointer))
    @rtype: 2-tuple of (function, (bytes, int))
    """
    return unpickleStringI, (stringi.getvalue(), stringi.tell())



def unpickleStringI(val, sek):
    """
    Convert the output of L{pickleStringI} into an appropriate type for the
    current Python version.

    This may be called on Python 3 and will convert a cStringIO into an
    L{io.StringIO}.

    @param val: The content of the file.
    @type val: L{bytes}

    @param sek: The seek position of the file.
    @type sek: L{int}

    @return: a file-like object which you can read bytes from.
    @rtype: L{cStringIO.OutputType} on Python 2, L{io.StringIO} on Python 3.
    """
    x = _cStringIO(val)
    x.seek(sek)
    return x



try:
    from cStringIO import InputType, OutputType, StringIO as _cStringIO
except ImportError:
    from io import StringIO as _cStringIO
else:
    copy_reg.pickle(OutputType, pickleStringO, unpickleStringO)
    copy_reg.pickle(InputType, pickleStringI, unpickleStringI)



class Ephemeral:
    """
    This type of object is never persisted; if possible, even references to it
    are eliminated.
    """

    def __reduce__(self):
        """
        Serialize any subclass of L{Ephemeral} in a way which replaces it with
        L{Ephemeral} itself.
        """
        return (Ephemeral, ())

    def __getstate__(self):
        log.msg( "WARNING: serializing ephemeral %s" % self )
        if not _PYPY:
            import gc
            if getattr(gc, 'get_referrers', None):
                for r in gc.get_referrers(self):
                    log.msg( " referred to by %s" % (r,))
        return None

    def __setstate__(self, state):
        log.msg( "WARNING: unserializing ephemeral %s" % self.__class__ )
        self.__class__ = Ephemeral


versionedsToUpgrade = {}
upgraded = {}

def doUpgrade():
    global versionedsToUpgrade, upgraded
    for versioned in list(versionedsToUpgrade.values()):
        requireUpgrade(versioned)
    versionedsToUpgrade = {}
    upgraded = {}

def requireUpgrade(obj):
    """Require that a Versioned instance be upgraded completely first.
    """
    objID = id(obj)
    if objID in versionedsToUpgrade and objID not in upgraded:
        upgraded[objID] = 1
        obj.versionUpgrade()
        return obj

def _aybabtu(c):
    """
    Get all of the parent classes of C{c}, not including C{c} itself, which are
    strict subclasses of L{Versioned}.

    @param c: a class
    @returns: list of classes
    """
    # begin with two classes that should *not* be included in the
    # final result
    l = [c, Versioned]
    for b in inspect.getmro(c):
        if b not in l and issubclass(b, Versioned):
            l.append(b)
    # return all except the unwanted classes
    return l[2:]

class Versioned:
    """
    This type of object is persisted with versioning information.

    I have a single class attribute, the int persistenceVersion.  After I am
    unserialized (and styles.doUpgrade() is called), self.upgradeToVersionX()
    will be called for each version upgrade I must undergo.

    For example, if I serialize an instance of a Foo(Versioned) at version 4
    and then unserialize it when the code is at version 9, the calls::

      self.upgradeToVersion5()
      self.upgradeToVersion6()
      self.upgradeToVersion7()
      self.upgradeToVersion8()
      self.upgradeToVersion9()

    will be made.  If any of these methods are undefined, a warning message
    will be printed.
    """
    persistenceVersion = 0
    persistenceForgets = ()

    def __setstate__(self, state):
        versionedsToUpgrade[id(self)] = self
        self.__dict__ = state

    def __getstate__(self, dict=None):
        """Get state, adding a version number to it on its way out.
        """
        dct = copy.copy(dict or self.__dict__)
        bases = _aybabtu(self.__class__)
        bases.reverse()
        bases.append(self.__class__) # don't forget me!!
        for base in bases:
            if 'persistenceForgets' in base.__dict__:
                for slot in base.persistenceForgets:
                    if slot in dct:
                        del dct[slot]
            if 'persistenceVersion' in base.__dict__:
                dct['%s.persistenceVersion' % reflect.qual(base)] = base.persistenceVersion
        return dct

    def versionUpgrade(self):
        """(internal) Do a version upgrade.
        """
        bases = _aybabtu(self.__class__)
        # put the bases in order so superclasses' persistenceVersion methods
        # will be called first.
        bases.reverse()
        bases.append(self.__class__) # don't forget me!!
        # first let's look for old-skool versioned's
        if "persistenceVersion" in self.__dict__:

            # Hacky heuristic: if more than one class subclasses Versioned,
            # we'll assume that the higher version number wins for the older
            # class, so we'll consider the attribute the version of the older
            # class.  There are obviously possibly times when this will
            # eventually be an incorrect assumption, but hopefully old-school
            # persistenceVersion stuff won't make it that far into multiple
            # classes inheriting from Versioned.

            pver = self.__dict__['persistenceVersion']
            del self.__dict__['persistenceVersion']
            highestVersion = 0
            highestBase = None
            for base in bases:
                if 'persistenceVersion' not in base.__dict__:
                    continue
                if base.persistenceVersion > highestVersion:
                    highestBase = base
                    highestVersion = base.persistenceVersion
            if highestBase:
                self.__dict__['%s.persistenceVersion' % reflect.qual(highestBase)] = pver
        for base in bases:
            # ugly hack, but it's what the user expects, really
            if (Versioned not in base.__bases__ and
                'persistenceVersion' not in base.__dict__):
                continue
            currentVers = base.persistenceVersion
            pverName = '%s.persistenceVersion' % reflect.qual(base)
            persistVers = (self.__dict__.get(pverName) or 0)
            if persistVers:
                del self.__dict__[pverName]
            assert persistVers <=  currentVers, "Sorry, can't go backwards in time."
            while persistVers < currentVers:
                persistVers = persistVers + 1
                method = base.__dict__.get('upgradeToVersion%s' % persistVers, None)
                if method:
                    log.msg( "Upgrading %s (of %s @ %s) to version %s" % (reflect.qual(base), reflect.qual(self.__class__), id(self), persistVers) )
                    method(self)
                else:
                    log.msg( 'Warning: cannot upgrade %s to version %s' % (base, persistVers) )

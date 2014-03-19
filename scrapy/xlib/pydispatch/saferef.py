"""Refactored "safe reference" from dispatcher.py"""
from __future__ import print_function
import weakref
import traceback


def safeRef(target, onDelete=None):
    """Return a *safe* weak reference to a callable target

    target -- the object to be weakly referenced, if it's a
            bound method reference, will create a BoundMethodWeakref,
            otherwise creates a simple weakref.
    onDelete -- if provided, will have a hard reference stored
            to the callable to be called after the safe reference
            goes out of scope with the reference object, (either a
            weakref or a BoundMethodWeakref) as argument.
    """
    if hasattr(target, 'im_self'):
        if target.im_self is not None:
            # Turn a bound method into a BoundMethodWeakref instance.
            # Keep track of these instances for lookup by disconnect().
            assert hasattr(
                target, 'im_func'), """safeRef target %r has im_self, but no im_func, don't know how to create reference""" % ( target,)
            reference = BoundMethodWeakref(
                target=target,
                onDelete=onDelete
            )
            return reference
    if onDelete is not None:
        return weakref.ref(target, onDelete)
    else:
        return weakref.ref(target)


class BoundMethodWeakref(object):

    """'Safe' and reusable weak references to instance methods

    BoundMethodWeakref objects provide a mechanism for
    referencing a bound method without requiring that the
    method object itself (which is normally a transient
    object) is kept alive.  Instead, the BoundMethodWeakref
    object keeps weak references to both the object and the
    function which together define the instance method.

    Attributes:
            key -- the identity key for the reference, calculated
                    by the class's calculateKey method applied to the
                    target instance method
            deletionMethods -- sequence of callable objects taking
                    single argument, a reference to this object which
                    will be called when *either* the target object or
                    target function is garbage collected (i.e. when
                    this object becomes invalid).  These are specified
                    as the onDelete parameters of safeRef calls.
            weakSelf -- weak reference to the target object
            weakFunc -- weak reference to the target function

    Class Attributes:
            _allInstances -- class attribute pointing to all live
                    BoundMethodWeakref objects indexed by the class's
                    calculateKey(target) method applied to the target
                    objects.  This weak value dictionary is used to
                    short-circuit creation so that multiple references
                    to the same (object, function) pair produce the
                    same BoundMethodWeakref instance.

    """
    _allInstances = weakref.WeakValueDictionary()

    def __new__(cls, target, onDelete=None, *arguments, **named):
        """Create new instance or return current instance

        Basically this method of construction allows us to
        short-circuit creation of references to already-
        referenced instance methods.  The key corresponding
        to the target is calculated, and if there is already
        an existing reference, that is returned, with its
        deletionMethods attribute updated.  Otherwise the
        new instance is created and registered in the table
        of already-referenced methods.
        """
        key = cls.calculateKey(target)
        current = cls._allInstances.get(key)
        if current is not None:
            current.deletionMethods.append(onDelete)
            return current
        else:
            base = super(BoundMethodWeakref, cls).__new__(cls)
            cls._allInstances[key] = base
            base.__init__(target, onDelete, *arguments, **named)
            return base

    def __init__(self, target, onDelete=None):
        """Return a weak-reference-like instance for a bound method

        target -- the instance-method target for the weak
                reference, must have im_self and im_func attributes
                and be reconstructable via:
                        target.im_func.__get__( target.im_self )
                which is true of built-in instance methods.
        onDelete -- optional callback which will be called
                when this weak reference ceases to be valid
                (i.e. either the object or the function is garbage
                collected).  Should take a single argument,
                which will be passed a pointer to this object.
        """
        def remove(weak, self=self):
            """Set self.isDead to true when method or instance is destroyed"""
            methods = self.deletionMethods[:]
            del self.deletionMethods[:]
            try:
                del self.__class__._allInstances[self.key]
            except KeyError:
                pass
            for function in methods:
                try:
                    if callable(function):
                        function(self)
                except Exception as e:
                    try:
                        traceback.print_exc()
                    except AttributeError as err:
                        print('''Exception during saferef %s cleanup function %s: %s''' % (
                            self, function, e
                        ))
        self.deletionMethods = [onDelete]
        self.key = self.calculateKey(target)
        self.weakSelf = weakref.ref(target.im_self, remove)
        self.weakFunc = weakref.ref(target.im_func, remove)
        self.selfName = target.im_self.__class__.__name__
        self.funcName = str(target.im_func.__name__)

    def calculateKey(cls, target):
        """Calculate the reference key for this reference

        Currently this is a two-tuple of the id()'s of the
        target object and the target function respectively.
        """
        return (id(target.im_self), id(target.im_func))
    calculateKey = classmethod(calculateKey)

    def __str__(self):
        """Give a friendly representation of the object"""
        return """%s( %s.%s )""" % (
            self.__class__.__name__,
            self.selfName,
            self.funcName,
        )
    __repr__ = __str__

    def __nonzero__(self):
        """Whether we are still a valid reference"""
        return self() is not None

    def __cmp__(self, other):
        """Compare with another reference"""
        if not isinstance(other, self.__class__):
            return cmp(self.__class__, type(other))
        return cmp(self.key, other.key)

    def __call__(self):
        """Return a strong reference to the bound method

        If the target cannot be retrieved, then will
        return None, otherwise returns a bound instance
        method for our object and function.

        Note:
                You may call this method any number of times,
                as it does not invalidate the reference.
        """
        target = self.weakSelf()
        if target is not None:
            function = self.weakFunc()
            if function is not None:
                return function.__get__(target)
        return None

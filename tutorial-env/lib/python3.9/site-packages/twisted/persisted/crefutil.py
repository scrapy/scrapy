# -*- test-case-name: twisted.test.test_persisted -*-

# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Utility classes for dealing with circular references.
"""


from twisted.python import log, reflect
from twisted.python.compat import _constructMethod


class NotKnown:
    def __init__(self):
        self.dependants = []
        self.resolved = 0

    def addDependant(self, mutableObject, key):
        assert not self.resolved
        self.dependants.append((mutableObject, key))

    resolvedObject = None

    def resolveDependants(self, newObject):
        self.resolved = 1
        self.resolvedObject = newObject
        for mut, key in self.dependants:
            mut[key] = newObject

    def __hash__(self):
        assert 0, "I am not to be used as a dictionary key."


class _Container(NotKnown):
    """
    Helper class to resolve circular references on container objects.
    """

    def __init__(self, l, containerType):
        """
        @param l: The list of object which may contain some not yet referenced
        objects.

        @param containerType: A type of container objects (e.g., C{tuple} or
            C{set}).
        """
        NotKnown.__init__(self)
        self.containerType = containerType
        self.l = l
        self.locs = list(range(len(l)))
        for idx in range(len(l)):
            if not isinstance(l[idx], NotKnown):
                self.locs.remove(idx)
            else:
                l[idx].addDependant(self, idx)
        if not self.locs:
            self.resolveDependants(self.containerType(self.l))

    def __setitem__(self, n, obj):
        """
        Change the value of one contained objects, and resolve references if
        all objects have been referenced.
        """
        self.l[n] = obj
        if not isinstance(obj, NotKnown):
            self.locs.remove(n)
            if not self.locs:
                self.resolveDependants(self.containerType(self.l))


class _Tuple(_Container):
    """
    Manage tuple containing circular references. Deprecated: use C{_Container}
    instead.
    """

    def __init__(self, l):
        """
        @param l: The list of object which may contain some not yet referenced
        objects.
        """
        _Container.__init__(self, l, tuple)


class _InstanceMethod(NotKnown):
    def __init__(self, im_name, im_self, im_class):
        NotKnown.__init__(self)
        self.my_class = im_class
        self.name = im_name
        # im_self _must_ be a NotKnown
        im_self.addDependant(self, 0)

    def __call__(self, *args, **kw):
        import traceback

        log.msg(f"instance method {reflect.qual(self.my_class)}.{self.name}")
        log.msg(f"being called with {args!r} {kw!r}")
        traceback.print_stack(file=log.logfile)
        assert 0

    def __setitem__(self, n, obj):
        assert n == 0, "only zero index allowed"
        if not isinstance(obj, NotKnown):
            method = _constructMethod(self.my_class, self.name, obj)
            self.resolveDependants(method)


class _DictKeyAndValue:
    def __init__(self, dict):
        self.dict = dict

    def __setitem__(self, n, obj):
        if n not in (1, 0):
            raise RuntimeError("DictKeyAndValue should only ever be called with 0 or 1")
        if n:  # value
            self.value = obj
        else:
            self.key = obj
        if hasattr(self, "key") and hasattr(self, "value"):
            self.dict[self.key] = self.value


class _Dereference(NotKnown):
    def __init__(self, id):
        NotKnown.__init__(self)
        self.id = id


from twisted.internet.defer import Deferred


class _Defer(Deferred[object], NotKnown):
    def __init__(self):
        Deferred.__init__(self)
        NotKnown.__init__(self)
        self.pause()

    wasset = 0

    def __setitem__(self, n, obj):
        if self.wasset:
            raise RuntimeError(
                "setitem should only be called once, setting {!r} to {!r}".format(
                    n, obj
                )
            )
        else:
            self.wasset = 1
        self.callback(obj)

    def addDependant(self, dep, key):
        # by the time I'm adding a dependant, I'm *not* adding any more
        # callbacks
        NotKnown.addDependant(self, dep, key)
        self.unpause()
        resovd = self.result
        self.resolveDependants(resovd)

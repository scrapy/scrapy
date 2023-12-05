# -*- test-case-name: twisted.spread.test.test_pb -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module represents flavors of remotely accessible objects.

Currently this is only objects accessible through Perspective Broker, but will
hopefully encompass all forms of remote access which can emulate subsets of PB
(such as XMLRPC or SOAP).

Future Plans: Optimization.  Exploitation of new-style object model.
Optimizations to this module should not affect external-use semantics at all,
but may have a small impact on users who subclass and override methods.

@author: Glyph Lefkowitz
"""


# NOTE: this module should NOT import pb; it is supposed to be a module which
# abstractly defines remotely accessible types.  Many of these types expect to
# be serialized by Jelly, but they ought to be accessible through other
# mechanisms (like XMLRPC)

import sys

from zope.interface import Interface, implementer

from twisted.python import log, reflect
from twisted.python.compat import cmp, comparable
from .jelly import (
    Jellyable,
    Unjellyable,
    _createBlank,
    getInstanceState,
    setInstanceState,
    setUnjellyableFactoryForClass,
    setUnjellyableForClass,
    setUnjellyableForClassTree,
    unjellyableRegistry,
)

# compatibility
setCopierForClass = setUnjellyableForClass
setCopierForClassTree = setUnjellyableForClassTree
setFactoryForClass = setUnjellyableFactoryForClass
copyTags = unjellyableRegistry

copy_atom = b"copy"
cache_atom = b"cache"
cached_atom = b"cached"
remote_atom = b"remote"


class NoSuchMethod(AttributeError):
    """Raised if there is no such remote method"""


class IPBRoot(Interface):
    """Factory for root Referenceable objects for PB servers."""

    def rootObject(broker):
        """Return root Referenceable for broker."""


class Serializable(Jellyable):
    """An object that can be passed remotely.

    I am a style of object which can be serialized by Perspective
    Broker.  Objects which wish to be referenceable or copied remotely
    have to subclass Serializable.  However, clients of Perspective
    Broker will probably not want to directly subclass Serializable; the
    Flavors of transferable objects are listed below.

    What it means to be \"Serializable\" is that an object can be
    passed to or returned from a remote method.  Certain basic types
    (dictionaries, lists, tuples, numbers, strings) are serializable by
    default; however, classes need to choose a specific serialization
    style: L{Referenceable}, L{Viewable}, L{Copyable} or L{Cacheable}.

    You may also pass C{[lists, dictionaries, tuples]} of L{Serializable}
    instances to or return them from remote methods, as many levels deep
    as you like.
    """

    def processUniqueID(self):
        """Return an ID which uniquely represents this object for this process.

        By default, this uses the 'id' builtin, but can be overridden to
        indicate that two values are identity-equivalent (such as proxies
        for the same object).
        """

        return id(self)


class Referenceable(Serializable):
    perspective = None
    """I am an object sent remotely as a direct reference.

    When one of my subclasses is sent as an argument to or returned
    from a remote method call, I will be serialized by default as a
    direct reference.

    This means that the peer will be able to call methods on me;
    a method call xxx() from my peer will be resolved to methods
    of the name remote_xxx.
    """

    def remoteMessageReceived(self, broker, message, args, kw):
        """A remote message has been received.  Dispatch it appropriately.

        The default implementation is to dispatch to a method called
        'remote_messagename' and call it with the same arguments.
        """
        args = broker.unserialize(args)
        kw = broker.unserialize(kw)
        # Need this to interoperate with Python 2 clients
        # which may try to send use keywords where keys are of type
        # bytes.
        if [key for key in kw.keys() if isinstance(key, bytes)]:
            kw = {k.decode("utf8"): v for k, v in kw.items()}

        if not isinstance(message, str):
            message = message.decode("utf8")

        method = getattr(self, "remote_%s" % message, None)
        if method is None:
            raise NoSuchMethod(f"No such method: remote_{message}")
        try:
            state = method(*args, **kw)
        except TypeError:
            log.msg(f"{method} didn't accept {args} and {kw}")
            raise
        return broker.serialize(state, self.perspective)

    def jellyFor(self, jellier):
        """(internal)

        Return a tuple which will be used as the s-expression to
        serialize this to a peer.
        """

        return [b"remote", jellier.invoker.registerReference(self)]


@implementer(IPBRoot)
class Root(Referenceable):
    """I provide a root object to L{pb.Broker}s for a L{pb.PBClientFactory} or
    L{pb.PBServerFactory}.

    When a factory produces a L{pb.Broker}, it supplies that
    L{pb.Broker} with an object named \"root\".  That object is obtained
    by calling my rootObject method.
    """

    def rootObject(self, broker):
        """A factory is requesting to publish me as a root object.

        When a factory is sending me as the root object, this
        method will be invoked to allow per-broker versions of an
        object.  By default I return myself.
        """
        return self


class ViewPoint(Referenceable):
    """
    I act as an indirect reference to an object accessed through a
    L{pb.IPerspective}.

    Simply put, I combine an object with a perspective so that when a
    peer calls methods on the object I refer to, the method will be
    invoked with that perspective as a first argument, so that it can
    know who is calling it.

    While L{Viewable} objects will be converted to ViewPoints by default
    when they are returned from or sent as arguments to a remote
    method, any object may be manually proxied as well. (XXX: Now that
    this class is no longer named C{Proxy}, this is the only occurrence
    of the term 'proxied' in this docstring, and may be unclear.)

    This can be useful when dealing with L{pb.IPerspective}s, L{Copyable}s,
    and L{Cacheable}s.  It is legal to implement a method as such on
    a perspective::

     | def perspective_getViewPointForOther(self, name):
     |     defr = self.service.getPerspectiveRequest(name)
     |     defr.addCallbacks(lambda x, self=self: ViewPoint(self, x), log.msg)
     |     return defr

    This will allow you to have references to Perspective objects in two
    different ways.  One is through the initial 'attach' call -- each
    peer will have a L{pb.RemoteReference} to their perspective directly.  The
    other is through this method; each peer can get a L{pb.RemoteReference} to
    all other perspectives in the service; but that L{pb.RemoteReference} will
    be to a L{ViewPoint}, not directly to the object.

    The practical offshoot of this is that you can implement 2 varieties
    of remotely callable methods on this Perspective; view_xxx and
    C{perspective_xxx}. C{view_xxx} methods will follow the rules for
    ViewPoint methods (see ViewPoint.L{remoteMessageReceived}), and
    C{perspective_xxx} methods will follow the rules for Perspective
    methods.
    """

    def __init__(self, perspective, object):
        """Initialize me with a Perspective and an Object."""
        self.perspective = perspective
        self.object = object

    def processUniqueID(self):
        """Return an ID unique to a proxy for this perspective+object combination."""
        return (id(self.perspective), id(self.object))

    def remoteMessageReceived(self, broker, message, args, kw):
        """A remote message has been received.  Dispatch it appropriately.

        The default implementation is to dispatch to a method called
        'C{view_messagename}' to my Object and call it on my object with
        the same arguments, modified by inserting my Perspective as
        the first argument.
        """
        args = broker.unserialize(args, self.perspective)
        kw = broker.unserialize(kw, self.perspective)

        if not isinstance(message, str):
            message = message.decode("utf8")

        method = getattr(self.object, "view_%s" % message)
        try:
            state = method(*(self.perspective,) + args, **kw)
        except TypeError:
            log.msg(f"{method} didn't accept {args} and {kw}")
            raise
        rv = broker.serialize(state, self.perspective, method, args, kw)
        return rv


class Viewable(Serializable):
    """I will be converted to a L{ViewPoint} when passed to or returned from a remote method.

    The beginning of a peer's interaction with a PB Service is always
    through a perspective.  However, if a C{perspective_xxx} method returns
    a Viewable, it will be serialized to the peer as a response to that
    method.
    """

    def jellyFor(self, jellier):
        """Serialize a L{ViewPoint} for me and the perspective of the given broker."""
        return ViewPoint(jellier.invoker.serializingPerspective, self).jellyFor(jellier)


class Copyable(Serializable):
    """Subclass me to get copied each time you are returned from or passed to a remote method.

    When I am returned from or passed to a remote method call, I will be
    converted into data via a set of callbacks (see my methods for more
    info).  That data will then be serialized using Jelly, and sent to
    the peer.

    The peer will then look up the type to represent this with; see
    L{RemoteCopy} for details.
    """

    def getStateToCopy(self):
        """Gather state to send when I am serialized for a peer.

        I will default to returning self.__dict__.  Override this to
        customize this behavior.
        """

        return self.__dict__

    def getStateToCopyFor(self, perspective):
        """
        Gather state to send when I am serialized for a particular
        perspective.

        I will default to calling L{getStateToCopy}.  Override this to
        customize this behavior.
        """

        return self.getStateToCopy()

    def getTypeToCopy(self):
        """Determine what type tag to send for me.

        By default, send the string representation of my class
        (package.module.Class); normally this is adequate, but
        you may override this to change it.
        """

        return reflect.qual(self.__class__).encode("utf-8")

    def getTypeToCopyFor(self, perspective):
        """Determine what type tag to send for me.

        By default, defer to self.L{getTypeToCopy}() normally this is
        adequate, but you may override this to change it.
        """

        return self.getTypeToCopy()

    def jellyFor(self, jellier):
        """Assemble type tag and state to copy for this broker.

        This will call L{getTypeToCopyFor} and L{getStateToCopy}, and
        return an appropriate s-expression to represent me.
        """

        if jellier.invoker is None:
            return getInstanceState(self, jellier)
        p = jellier.invoker.serializingPerspective
        t = self.getTypeToCopyFor(p)
        state = self.getStateToCopyFor(p)
        sxp = jellier.prepare(self)
        sxp.extend([t, jellier.jelly(state)])
        return jellier.preserve(self, sxp)


class Cacheable(Copyable):
    """A cached instance.

    This means that it's copied; but there is some logic to make sure
    that it's only copied once.  Additionally, when state is retrieved,
    it is passed a "proto-reference" to the state as it will exist on
    the client.

    XXX: The documentation for this class needs work, but it's the most
    complex part of PB and it is inherently difficult to explain.
    """

    def getStateToCacheAndObserveFor(self, perspective, observer):
        """
        Get state to cache on the client and client-cache reference
        to observe locally.

        This is similar to getStateToCopyFor, but it additionally
        passes in a reference to the client-side RemoteCache instance
        that will be created when it is unserialized.  This allows
        Cacheable instances to keep their RemoteCaches up to date when
        they change, such that no changes can occur between the point
        at which the state is initially copied and the client receives
        it that are not propagated.
        """

        return self.getStateToCopyFor(perspective)

    def jellyFor(self, jellier):
        """Return an appropriate tuple to serialize me.

        Depending on whether this broker has cached me or not, this may
        return either a full state or a reference to an existing cache.
        """
        if jellier.invoker is None:
            return getInstanceState(self, jellier)
        luid = jellier.invoker.cachedRemotelyAs(self, 1)
        if luid is None:
            luid = jellier.invoker.cacheRemotely(self)
            p = jellier.invoker.serializingPerspective
            type_ = self.getTypeToCopyFor(p)
            observer = RemoteCacheObserver(jellier.invoker, self, p)
            state = self.getStateToCacheAndObserveFor(p, observer)
            l = jellier.prepare(self)
            jstate = jellier.jelly(state)
            l.extend([type_, luid, jstate])
            return jellier.preserve(self, l)
        else:
            return cached_atom, luid

    def stoppedObserving(self, perspective, observer):
        """This method is called when a client has stopped observing me.

        The 'observer' argument is the same as that passed in to
        getStateToCacheAndObserveFor.
        """


class RemoteCopy(Unjellyable):
    """I am a remote copy of a Copyable object.

    When the state from a L{Copyable} object is received, an instance will
    be created based on the copy tags table (see setUnjellyableForClass) and
    sent the L{setCopyableState} message.  I provide a reasonable default
    implementation of that message; subclass me if you wish to serve as
    a copier for remote data.

    NOTE: copiers are invoked with no arguments.  Do not implement a
    constructor which requires args in a subclass of L{RemoteCopy}!
    """

    def setCopyableState(self, state):
        """I will be invoked with the state to copy locally.

        'state' is the data returned from the remote object's
        'getStateToCopyFor' method, which will often be the remote
        object's dictionary (or a filtered approximation of it depending
        on my peer's perspective).
        """
        state = {
            x.decode("utf8") if isinstance(x, bytes) else x: y for x, y in state.items()
        }
        self.__dict__ = state

    def unjellyFor(self, unjellier, jellyList):
        if unjellier.invoker is None:
            return setInstanceState(self, unjellier, jellyList)
        self.setCopyableState(unjellier.unjelly(jellyList[1]))
        return self


class RemoteCache(RemoteCopy, Serializable):
    """A cache is a local representation of a remote L{Cacheable} object.

    This represents the last known state of this object.  It may
    also have methods invoked on it -- in order to update caches,
    the cached class generates a L{pb.RemoteReference} to this object as
    it is originally sent.

    Much like copy, I will be invoked with no arguments.  Do not
    implement a constructor that requires arguments in one of my
    subclasses.
    """

    def remoteMessageReceived(self, broker, message, args, kw):
        """A remote message has been received.  Dispatch it appropriately.

        The default implementation is to dispatch to a method called
        'C{observe_messagename}' and call it on my  with the same arguments.
        """
        if not isinstance(message, str):
            message = message.decode("utf8")

        args = broker.unserialize(args)
        kw = broker.unserialize(kw)
        method = getattr(self, "observe_%s" % message)
        try:
            state = method(*args, **kw)
        except TypeError:
            log.msg(f"{method} didn't accept {args} and {kw}")
            raise
        return broker.serialize(state, None, method, args, kw)

    def jellyFor(self, jellier):
        """serialize me (only for the broker I'm for) as the original cached reference"""
        if jellier.invoker is None:
            return getInstanceState(self, jellier)
        assert (
            jellier.invoker is self.broker
        ), "You cannot exchange cached proxies between brokers."
        return b"lcache", self.luid

    def unjellyFor(self, unjellier, jellyList):
        if unjellier.invoker is None:
            return setInstanceState(self, unjellier, jellyList)
        self.broker = unjellier.invoker
        self.luid = jellyList[1]
        borgCopy = self._borgify()
        # XXX questionable whether this was a good design idea...
        init = getattr(borgCopy, "__init__", None)
        if init:
            init()
        unjellier.invoker.cacheLocally(jellyList[1], self)
        borgCopy.setCopyableState(unjellier.unjelly(jellyList[2]))
        # Might have changed due to setCopyableState method; we'll assume that
        # it's bad form to do so afterwards.
        self.__dict__ = borgCopy.__dict__
        # chomp, chomp -- some existing code uses "self.__dict__ =", some uses
        # "__dict__.update".  This is here in order to handle both cases.
        self.broker = unjellier.invoker
        self.luid = jellyList[1]
        return borgCopy

    ##     def __really_del__(self):
    ##         """Final finalization call, made after all remote references have been lost.
    ##         """

    def __cmp__(self, other):
        """Compare me [to another RemoteCache."""
        if isinstance(other, self.__class__):
            return cmp(id(self.__dict__), id(other.__dict__))
        else:
            return cmp(id(self.__dict__), other)

    def __hash__(self):
        """Hash me."""
        return int(id(self.__dict__) % sys.maxsize)

    broker = None
    luid = None

    def __del__(self):
        """Do distributed reference counting on finalize."""
        try:
            # log.msg( ' --- decache: %s %s' % (self, self.luid) )
            if self.broker:
                self.broker.decCacheRef(self.luid)
        except BaseException:
            log.deferr()

    def _borgify(self):
        """
        Create a new object that shares its state (i.e. its C{__dict__}) and
        type with this object, but does not share its identity.

        This is an instance of U{the Borg design pattern
        <https://code.activestate.com/recipes/66531/>} originally described by
        Alex Martelli, but unlike the example given there, this is not a
        replacement for a Singleton.  Instead, it is for lifecycle tracking
        (and distributed garbage collection).  The purpose of these separate
        objects is to have a separate object tracking each application-level
        reference to the root L{RemoteCache} object being tracked by the
        broker, and to have their C{__del__} methods be invoked.

        This may be achievable via a weak value dictionary to track the root
        L{RemoteCache} instances instead, but this implementation strategy
        predates the availability of weak references in Python.

        @return: The new instance.
        @rtype: C{self.__class__}
        """
        blank = _createBlank(self.__class__)
        blank.__dict__ = self.__dict__
        return blank


def unjellyCached(unjellier, unjellyList):
    luid = unjellyList[1]
    return unjellier.invoker.cachedLocallyAs(luid)._borgify()


setUnjellyableForClass("cached", unjellyCached)


def unjellyLCache(unjellier, unjellyList):
    luid = unjellyList[1]
    obj = unjellier.invoker.remotelyCachedForLUID(luid)
    return obj


setUnjellyableForClass("lcache", unjellyLCache)


def unjellyLocal(unjellier, unjellyList):
    obj = unjellier.invoker.localObjectForID(unjellyList[1])
    return obj


setUnjellyableForClass("local", unjellyLocal)


@comparable
class RemoteCacheMethod:
    """A method on a reference to a L{RemoteCache}."""

    def __init__(self, name, broker, cached, perspective):
        """(internal) initialize."""
        self.name = name
        self.broker = broker
        self.perspective = perspective
        self.cached = cached

    def __cmp__(self, other):
        return cmp((self.name, self.broker, self.perspective, self.cached), other)

    def __hash__(self):
        return hash((self.name, self.broker, self.perspective, self.cached))

    def __call__(self, *args, **kw):
        """(internal) action method."""
        cacheID = self.broker.cachedRemotelyAs(self.cached)
        if cacheID is None:
            from pb import ProtocolError  # type: ignore[import]

            raise ProtocolError(
                "You can't call a cached method when the object hasn't been given to the peer yet."
            )
        return self.broker._sendMessage(
            b"cache", self.perspective, cacheID, self.name, args, kw
        )


@comparable
class RemoteCacheObserver:
    """I am a reverse-reference to the peer's L{RemoteCache}.

    I am generated automatically when a cache is serialized.  I
    represent a reference to the client's L{RemoteCache} object that
    will represent a particular L{Cacheable}; I am the additional
    object passed to getStateToCacheAndObserveFor.
    """

    def __init__(self, broker, cached, perspective):
        """(internal) Initialize me.

        @param broker: a L{pb.Broker} instance.

        @param cached: a L{Cacheable} instance that this L{RemoteCacheObserver}
            corresponds to.

        @param perspective: a reference to the perspective who is observing this.
        """

        self.broker = broker
        self.cached = cached
        self.perspective = perspective

    def __repr__(self) -> str:
        return "<RemoteCacheObserver({}, {}, {}) at {}>".format(
            self.broker,
            self.cached,
            self.perspective,
            id(self),
        )

    def __hash__(self):
        """Generate a hash unique to all L{RemoteCacheObserver}s for this broker/perspective/cached triplet"""

        return (
            (hash(self.broker) % 2 ** 10)
            + (hash(self.perspective) % 2 ** 10)
            + (hash(self.cached) % 2 ** 10)
        )

    def __cmp__(self, other):
        """Compare me to another L{RemoteCacheObserver}."""

        return cmp((self.broker, self.perspective, self.cached), other)

    def callRemote(self, _name, *args, **kw):
        """(internal) action method."""
        cacheID = self.broker.cachedRemotelyAs(self.cached)
        if isinstance(_name, str):
            _name = _name.encode("utf-8")
        if cacheID is None:
            from pb import ProtocolError

            raise ProtocolError(
                "You can't call a cached method when the "
                "object hasn't been given to the peer yet."
            )
        return self.broker._sendMessage(
            b"cache", self.perspective, cacheID, _name, args, kw
        )

    def remoteMethod(self, key):
        """Get a L{pb.RemoteMethod} for this key."""
        return RemoteCacheMethod(key, self.broker, self.cached, self.perspective)

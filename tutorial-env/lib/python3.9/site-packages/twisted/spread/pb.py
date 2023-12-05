# -*- test-case-name: twisted.spread.test.test_pb -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Perspective Broker

\"This isn\'t a professional opinion, but it's probably got enough
internet to kill you.\" --glyph

Introduction
============

This is a broker for proxies for and copies of objects.  It provides a
translucent interface layer to those proxies.

The protocol is not opaque, because it provides objects which represent the
remote proxies and require no context (server references, IDs) to operate on.

It is not transparent because it does I{not} attempt to make remote objects
behave identically, or even similarly, to local objects.  Method calls are
invoked asynchronously, and specific rules are applied when serializing
arguments.

To get started, begin with L{PBClientFactory} and L{PBServerFactory}.

@author: Glyph Lefkowitz
"""


import random
from hashlib import md5

from zope.interface import Interface, implementer

from twisted.cred.credentials import (
    Anonymous,
    IAnonymous,
    ICredentials,
    IUsernameHashedPassword,
)
from twisted.cred.portal import Portal
from twisted.internet import defer, protocol
from twisted.persisted import styles

# Twisted Imports
from twisted.python import failure, log, reflect
from twisted.python.compat import cmp, comparable
from twisted.python.components import registerAdapter
from twisted.spread import banana

# These three are backwards compatibility aliases for the previous three.
# Ultimately they should be deprecated. -exarkun
from twisted.spread.flavors import (
    Cacheable,
    Copyable,
    IPBRoot,
    Jellyable,
    NoSuchMethod,
    Referenceable,
    RemoteCache,
    RemoteCacheObserver,
    RemoteCopy,
    Root,
    Serializable,
    Viewable,
    ViewPoint,
    copyTags,
    setCopierForClass,
    setCopierForClassTree,
    setFactoryForClass,
    setUnjellyableFactoryForClass,
    setUnjellyableForClass,
    setUnjellyableForClassTree,
)
from twisted.spread.interfaces import IJellyable, IUnjellyable
from twisted.spread.jelly import _newInstance, globalSecurity, jelly, unjelly

MAX_BROKER_REFS = 1024

portno = 8787


class ProtocolError(Exception):
    """
    This error is raised when an invalid protocol statement is received.
    """


class DeadReferenceError(ProtocolError):
    """
    This error is raised when a method is called on a dead reference (one whose
    broker has been disconnected).
    """


class Error(Exception):
    """
    This error can be raised to generate known error conditions.

    When a PB callable method (perspective_, remote_, view_) raises
    this error, it indicates that a traceback should not be printed,
    but instead, the string representation of the exception should be
    sent.
    """


class RemoteError(Exception):
    """
    This class is used to wrap a string-ified exception from the remote side to
    be able to reraise it. (Raising string exceptions is no longer possible in
    Python 2.6+)

    The value of this exception will be a str() representation of the remote
    value.

    @ivar remoteType: The full import path of the exception class which was
        raised on the remote end.
    @type remoteType: C{str}

    @ivar remoteTraceback: The remote traceback.
    @type remoteTraceback: C{str}

    @note: It's not possible to include the remoteTraceback if this exception is
        thrown into a generator. It must be accessed as an attribute.
    """

    def __init__(self, remoteType, value, remoteTraceback):
        Exception.__init__(self, value)
        self.remoteType = remoteType
        self.remoteTraceback = remoteTraceback


@comparable
class RemoteMethod:
    """
    This is a translucent reference to a remote message.
    """

    def __init__(self, obj, name):
        """
        Initialize with a L{RemoteReference} and the name of this message.
        """
        self.obj = obj
        self.name = name

    def __cmp__(self, other):
        return cmp((self.obj, self.name), other)

    def __hash__(self):
        return hash((self.obj, self.name))

    def __call__(self, *args, **kw):
        """
        Asynchronously invoke a remote method.
        """
        return self.obj.broker._sendMessage(
            b"",
            self.obj.perspective,
            self.obj.luid,
            self.name.encode("utf-8"),
            args,
            kw,
        )


class PBConnectionLost(Exception):
    pass


class IPerspective(Interface):
    """
    per*spec*tive, n. : The relationship of aspects of a subject to each
    other and to a whole: 'a perspective of history'; 'a need to view
    the problem in the proper perspective'.

    This is a Perspective Broker-specific wrapper for an avatar. That
    is to say, a PB-published view on to the business logic for the
    system's concept of a 'user'.

    The concept of attached/detached is no longer implemented by the
    framework. The realm is expected to implement such semantics if
    needed.
    """

    def perspectiveMessageReceived(broker, message, args, kwargs):
        """
        This method is called when a network message is received.

        @arg broker: The Perspective Broker.

        @type message: str
        @arg message: The name of the method called by the other end.

        @type args: list in jelly format
        @arg args: The arguments that were passed by the other end. It
                   is recommend that you use the `unserialize' method of the
                   broker to decode this.

        @type kwargs: dict in jelly format
        @arg kwargs: The keyword arguments that were passed by the
                     other end.  It is recommended that you use the
                     `unserialize' method of the broker to decode this.

        @rtype: A jelly list.
        @return: It is recommended that you use the `serialize' method
                 of the broker on whatever object you need to return to
                 generate the return value.
        """


@implementer(IPerspective)
class Avatar:
    """
    A default IPerspective implementor.

    This class is intended to be subclassed, and a realm should return
    an instance of such a subclass when IPerspective is requested of
    it.

    A peer requesting a perspective will receive only a
    L{RemoteReference} to a pb.Avatar.  When a method is called on
    that L{RemoteReference}, it will translate to a method on the
    remote perspective named 'perspective_methodname'.  (For more
    information on invoking methods on other objects, see
    L{flavors.ViewPoint}.)
    """

    def perspectiveMessageReceived(self, broker, message, args, kw):
        """
        This method is called when a network message is received.

        This will call::

            self.perspective_%(message)s(*broker.unserialize(args),
                                         **broker.unserialize(kw))

        to handle the method; subclasses of Avatar are expected to
        implement methods using this naming convention.
        """

        args = broker.unserialize(args, self)
        kw = broker.unserialize(kw, self)
        method = getattr(self, "perspective_%s" % message)
        try:
            state = method(*args, **kw)
        except TypeError:
            log.msg(f"{method} didn't accept {args} and {kw}")
            raise
        return broker.serialize(state, self, method, args, kw)


class AsReferenceable(Referenceable):
    """
    A reference directed towards another object.
    """

    def __init__(self, object, messageType="remote"):
        self.remoteMessageReceived = getattr(object, messageType + "MessageReceived")


@implementer(IUnjellyable)
@comparable
class RemoteReference(Serializable, styles.Ephemeral):
    """
    A translucent reference to a remote object.

    I may be a reference to a L{flavors.ViewPoint}, a
    L{flavors.Referenceable}, or an L{IPerspective} implementer (e.g.,
    pb.Avatar).  From the client's perspective, it is not possible to
    tell which except by convention.

    I am a \"translucent\" reference because although no additional
    bookkeeping overhead is given to the application programmer for
    manipulating a reference, return values are asynchronous.

    See also L{twisted.internet.defer}.

    @ivar broker: The broker I am obtained through.
    @type broker: L{Broker}
    """

    def __init__(self, perspective, broker, luid, doRefCount):
        """(internal) Initialize me with a broker and a locally-unique ID.

        The ID is unique only to the particular Perspective Broker
        instance.
        """
        self.luid = luid
        self.broker = broker
        self.doRefCount = doRefCount
        self.perspective = perspective
        self.disconnectCallbacks = []

    def notifyOnDisconnect(self, callback):
        """
        Register a callback to be called if our broker gets disconnected.

        @param callback: a callable which will be called with one
                         argument, this instance.
        """
        assert callable(callback)
        self.disconnectCallbacks.append(callback)
        if len(self.disconnectCallbacks) == 1:
            self.broker.notifyOnDisconnect(self._disconnected)

    def dontNotifyOnDisconnect(self, callback):
        """
        Remove a callback that was registered with notifyOnDisconnect.

        @param callback: a callable
        """
        self.disconnectCallbacks.remove(callback)
        if not self.disconnectCallbacks:
            self.broker.dontNotifyOnDisconnect(self._disconnected)

    def _disconnected(self):
        """
        Called if we are disconnected and have callbacks registered.
        """
        for callback in self.disconnectCallbacks:
            callback(self)
        self.disconnectCallbacks = None

    def jellyFor(self, jellier):
        """
        If I am being sent back to where I came from, serialize as a local backreference.
        """
        if jellier.invoker:
            assert (
                self.broker == jellier.invoker
            ), "Can't send references to brokers other than their own."
            return b"local", self.luid
        else:
            return b"unpersistable", "References cannot be serialized"

    def unjellyFor(self, unjellier, unjellyList):
        self.__init__(
            unjellier.invoker.unserializingPerspective,
            unjellier.invoker,
            unjellyList[1],
            1,
        )
        return self

    def callRemote(self, _name, *args, **kw):
        """
        Asynchronously invoke a remote method.

        @type _name: L{str}
        @param _name:  the name of the remote method to invoke
        @param args: arguments to serialize for the remote function
        @param kw:  keyword arguments to serialize for the remote function.
        @rtype:   L{twisted.internet.defer.Deferred}
        @returns: a Deferred which will be fired when the result of
                  this remote call is received.
        """
        if not isinstance(_name, bytes):
            _name = _name.encode("utf8")

        # Note that we use '_name' instead of 'name' so the user can call
        # remote methods with 'name' as a keyword parameter, like this:
        #  ref.callRemote("getPeopleNamed", count=12, name="Bob")
        return self.broker._sendMessage(
            b"", self.perspective, self.luid, _name, args, kw
        )

    def remoteMethod(self, key):
        """

        @param key: The key.
        @return: A L{RemoteMethod} for this key.
        """
        return RemoteMethod(self, key)

    def __cmp__(self, other):
        """

        @param other: another L{RemoteReference} to compare me to.
        """
        if isinstance(other, RemoteReference):
            if other.broker == self.broker:
                return cmp(self.luid, other.luid)
        return cmp(self.broker, other)

    def __hash__(self):
        """
        Hash me.
        """
        return self.luid

    def __del__(self):
        """
        Do distributed reference counting on finalization.
        """
        if self.doRefCount:
            self.broker.sendDecRef(self.luid)


setUnjellyableForClass("remote", RemoteReference)


class Local:
    """
    (internal) A reference to a local object.
    """

    def __init__(self, object, perspective=None):
        """
        Initialize.
        """
        self.object = object
        self.perspective = perspective
        self.refcount = 1

    def __repr__(self) -> str:
        return f"<pb.Local {self.object!r} ref:{self.refcount}>"

    def incref(self):
        """
        Increment the reference count.

        @return: the reference count after incrementing
        """
        self.refcount = self.refcount + 1
        return self.refcount

    def decref(self):
        """
        Decrement the reference count.

        @return: the reference count after decrementing
        """
        self.refcount = self.refcount - 1
        return self.refcount


# Failure
class CopyableFailure(failure.Failure, Copyable):
    """
    A L{flavors.RemoteCopy} and L{flavors.Copyable} version of
    L{twisted.python.failure.Failure} for serialization.
    """

    unsafeTracebacks = 0

    def getStateToCopy(self):
        """
        Collect state related to the exception which occurred, discarding
        state which cannot reasonably be serialized.
        """
        state = self.__dict__.copy()
        state["tb"] = None
        state["frames"] = []
        state["stack"] = []
        state["value"] = str(self.value)  # Exception instance
        if isinstance(self.type, bytes):
            state["type"] = self.type
        else:
            state["type"] = reflect.qual(self.type).encode("utf-8")  # Exception class
        if self.unsafeTracebacks:
            state["traceback"] = self.getTraceback()
        else:
            state["traceback"] = "Traceback unavailable\n"
        return state


class CopiedFailure(RemoteCopy, failure.Failure):
    """
    A L{CopiedFailure} is a L{pb.RemoteCopy} of a L{failure.Failure}
    transferred via PB.

    @ivar type: The full import path of the exception class which was raised on
        the remote end.
    @type type: C{str}

    @ivar value: A str() representation of the remote value.
    @type value: L{CopiedFailure} or C{str}

    @ivar traceback: The remote traceback.
    @type traceback: C{str}
    """

    def printTraceback(self, file=None, elideFrameworkCode=0, detail="default"):
        if file is None:
            file = log.logfile
        failureType = self.type
        if not isinstance(failureType, str):
            failureType = failureType.decode("utf-8")
        file.write("Traceback from remote host -- ")
        file.write(failureType + ": " + self.value)
        file.write("\n")

    def throwExceptionIntoGenerator(self, g):
        """
        Throw the original exception into the given generator, preserving
        traceback information if available. In the case of a L{CopiedFailure}
        where the exception type is a string, a L{pb.RemoteError} is thrown
        instead.

        @return: The next value yielded from the generator.
        @raise StopIteration: If there are no more values in the generator.
        @raise RemoteError: The wrapped remote exception.
        """
        return g.throw(RemoteError(self.type, self.value, self.traceback))

    printBriefTraceback = printTraceback
    printDetailedTraceback = printTraceback


setUnjellyableForClass(CopyableFailure, CopiedFailure)


def failure2Copyable(fail, unsafeTracebacks=0):
    f = _newInstance(CopyableFailure, fail.__dict__)
    f.unsafeTracebacks = unsafeTracebacks
    return f


class Broker(banana.Banana):
    """
    I am a broker for objects.
    """

    version = 6
    username = None
    factory = None

    def __init__(self, isClient=1, security=globalSecurity):
        banana.Banana.__init__(self, isClient)
        self.disconnected = 0
        self.disconnects = []
        self.failures = []
        self.connects = []
        self.localObjects = {}
        self.security = security
        self.pageProducers = []
        self.currentRequestID = 0
        self.currentLocalID = 0
        self.unserializingPerspective = None
        # Some terms:
        #  PUID: process unique ID; return value of id() function.  type "int".
        #  LUID: locally unique ID; an ID unique to an object mapped over this
        #        connection. type "int"
        #  GUID: (not used yet) globally unique ID; an ID for an object which
        #        may be on a redirected or meta server.  Type as yet undecided.
        # Dictionary mapping LUIDs to local objects.
        # set above to allow root object to be assigned before connection is made
        # self.localObjects = {}
        # Dictionary mapping PUIDs to LUIDs.
        self.luids = {}
        # Dictionary mapping LUIDs to local (remotely cached) objects. Remotely
        # cached means that they're objects which originate here, and were
        # copied remotely.
        self.remotelyCachedObjects = {}
        # Dictionary mapping PUIDs to (cached) LUIDs
        self.remotelyCachedLUIDs = {}
        # Dictionary mapping (remote) LUIDs to (locally cached) objects.
        self.locallyCachedObjects = {}
        self.waitingForAnswers = {}

        # Mapping from LUIDs to weakref objects with callbacks for performing
        # any local cleanup which may be necessary for the corresponding
        # object once it no longer exists.
        self._localCleanup = {}

    def resumeProducing(self):
        """
        Called when the consumer attached to me runs out of buffer.
        """
        # Go backwards over the list so we can remove indexes from it as we go
        for pageridx in range(len(self.pageProducers) - 1, -1, -1):
            pager = self.pageProducers[pageridx]
            pager.sendNextPage()
            if not pager.stillPaging():
                del self.pageProducers[pageridx]
        if not self.pageProducers:
            self.transport.unregisterProducer()

    def pauseProducing(self):
        # Streaming producer method; not necessary to implement.
        pass

    def stopProducing(self):
        # Streaming producer method; not necessary to implement.
        pass

    def registerPageProducer(self, pager):
        self.pageProducers.append(pager)
        if len(self.pageProducers) == 1:
            self.transport.registerProducer(self, 0)

    def expressionReceived(self, sexp):
        """
        Evaluate an expression as it's received.
        """
        if isinstance(sexp, list):
            command = sexp[0]

            if not isinstance(command, str):
                command = command.decode("utf8")

            methodName = "proto_%s" % command
            method = getattr(self, methodName, None)

            if method:
                method(*sexp[1:])
            else:
                self.sendCall(b"didNotUnderstand", command)
        else:
            raise ProtocolError("Non-list expression received.")

    def proto_version(self, vnum):
        """
        Protocol message: (version version-number)

        Check to make sure that both ends of the protocol are speaking
        the same version dialect.

        @param vnum: The version number.
        """

        if vnum != self.version:
            raise ProtocolError(f"Version Incompatibility: {self.version} {vnum}")

    def sendCall(self, *exp):
        """
        Utility method to send an expression to the other side of the connection.

        @param exp: The expression.
        """
        self.sendEncoded(exp)

    def proto_didNotUnderstand(self, command):
        """
        Respond to stock 'C{didNotUnderstand}' message.

        Log the command that was not understood and continue. (Note:
        this will probably be changed to close the connection or raise
        an exception in the future.)

        @param command: The command to log.
        """
        log.msg("Didn't understand command: %r" % command)

    def connectionReady(self):
        """
        Initialize. Called after Banana negotiation is done.
        """
        self.sendCall(b"version", self.version)
        for notifier in self.connects:
            try:
                notifier()
            except BaseException:
                log.deferr()
        self.connects = None
        self.factory.clientConnectionMade(self)

    def connectionFailed(self):
        # XXX should never get called anymore? check!
        for notifier in self.failures:
            try:
                notifier()
            except BaseException:
                log.deferr()
        self.failures = None

    waitingForAnswers = None

    def connectionLost(self, reason):
        """
        The connection was lost.

        @param reason: message to put in L{failure.Failure}
        """
        self.disconnected = 1
        # Nuke potential circular references.
        self.luids = None
        if self.waitingForAnswers:
            for d in self.waitingForAnswers.values():
                try:
                    d.errback(failure.Failure(PBConnectionLost(reason)))
                except BaseException:
                    log.deferr()
        # Assure all Cacheable.stoppedObserving are called
        for lobj in self.remotelyCachedObjects.values():
            cacheable = lobj.object
            perspective = lobj.perspective
            try:
                cacheable.stoppedObserving(
                    perspective, RemoteCacheObserver(self, cacheable, perspective)
                )
            except BaseException:
                log.deferr()
        # Loop on a copy to prevent notifiers to mixup
        # the list by calling dontNotifyOnDisconnect
        for notifier in self.disconnects[:]:
            try:
                notifier()
            except BaseException:
                log.deferr()
        self.disconnects = None
        self.waitingForAnswers = None
        self.localSecurity = None
        self.remoteSecurity = None
        self.remotelyCachedObjects = None
        self.remotelyCachedLUIDs = None
        self.locallyCachedObjects = None
        self.localObjects = None

    def notifyOnDisconnect(self, notifier):
        """

        @param notifier: callback to call when the Broker disconnects.
        """
        assert callable(notifier)
        self.disconnects.append(notifier)

    def notifyOnFail(self, notifier):
        """

        @param notifier: callback to call if the Broker fails to connect.
        """
        assert callable(notifier)
        self.failures.append(notifier)

    def notifyOnConnect(self, notifier):
        """

        @param notifier: callback to call when the Broker connects.
        """
        assert callable(notifier)
        if self.connects is None:
            try:
                notifier()
            except BaseException:
                log.err()
        else:
            self.connects.append(notifier)

    def dontNotifyOnDisconnect(self, notifier):
        """

        @param notifier: callback to remove from list of disconnect callbacks.
        """
        try:
            self.disconnects.remove(notifier)
        except ValueError:
            pass

    def localObjectForID(self, luid):
        """
        Get a local object for a locally unique ID.

        @return: An object previously stored with L{registerReference} or
            L{None} if there is no object which corresponds to the given
            identifier.
        """
        if isinstance(luid, str):
            luid = luid.encode("utf8")

        lob = self.localObjects.get(luid)
        if lob is None:
            return
        return lob.object

    maxBrokerRefsViolations = 0

    def registerReference(self, object):
        """
        Store a persistent reference to a local object and map its
        id() to a generated, session-unique ID.

        @param object: a local object
        @return: the generated ID
        """

        assert object is not None
        puid = object.processUniqueID()
        luid = self.luids.get(puid)
        if luid is None:
            if len(self.localObjects) > MAX_BROKER_REFS:
                self.maxBrokerRefsViolations = self.maxBrokerRefsViolations + 1
                if self.maxBrokerRefsViolations > 3:
                    self.transport.loseConnection()
                    raise Error("Maximum PB reference count exceeded.  " "Goodbye.")
                raise Error("Maximum PB reference count exceeded.")

            luid = self.newLocalID()
            self.localObjects[luid] = Local(object)
            self.luids[puid] = luid
        else:
            self.localObjects[luid].incref()
        return luid

    def setNameForLocal(self, name, object):
        """
        Store a special (string) ID for this object.

        This is how you specify a 'base' set of objects that the remote
        protocol can connect to.

        @param name: An ID.
        @param object: The object.
        """
        if isinstance(name, str):
            name = name.encode("utf8")

        assert object is not None
        self.localObjects[name] = Local(object)

    def remoteForName(self, name):
        """
        Returns an object from the remote name mapping.

        Note that this does not check the validity of the name, only
        creates a translucent reference for it.

        @param name: The name to look up.
        @return: An object which maps to the name.
        """
        if isinstance(name, str):
            name = name.encode("utf8")

        return RemoteReference(None, self, name, 0)

    def cachedRemotelyAs(self, instance, incref=0):
        """

        @param instance: The instance to look up.
        @param incref: Flag to specify whether to increment the
                       reference.
        @return: An ID that says what this instance is cached as
                 remotely, or L{None} if it's not.
        """

        puid = instance.processUniqueID()
        luid = self.remotelyCachedLUIDs.get(puid)
        if (luid is not None) and (incref):
            self.remotelyCachedObjects[luid].incref()
        return luid

    def remotelyCachedForLUID(self, luid):
        """

        @param luid: The LUID to look up.
        @return: An instance which is cached remotely.
        """
        return self.remotelyCachedObjects[luid].object

    def cacheRemotely(self, instance):
        """
        XXX

        @return: A new LUID.
        """
        puid = instance.processUniqueID()
        luid = self.newLocalID()
        if len(self.remotelyCachedObjects) > MAX_BROKER_REFS:
            self.maxBrokerRefsViolations = self.maxBrokerRefsViolations + 1
            if self.maxBrokerRefsViolations > 3:
                self.transport.loseConnection()
                raise Error("Maximum PB cache count exceeded.  " "Goodbye.")
            raise Error("Maximum PB cache count exceeded.")

        self.remotelyCachedLUIDs[puid] = luid
        # This table may not be necessary -- for now, it's to make sure that no
        # monkey business happens with id(instance)
        self.remotelyCachedObjects[luid] = Local(instance, self.serializingPerspective)
        return luid

    def cacheLocally(self, cid, instance):
        """(internal)

        Store a non-filled-out cached instance locally.
        """
        self.locallyCachedObjects[cid] = instance

    def cachedLocallyAs(self, cid):
        instance = self.locallyCachedObjects[cid]
        return instance

    def serialize(self, object, perspective=None, method=None, args=None, kw=None):
        """
        Jelly an object according to the remote security rules for this broker.

        @param object: The object to jelly.
        @param perspective: The perspective.
        @param method: The method.
        @param args: Arguments.
        @param kw: Keyword arguments.
        """

        if isinstance(object, defer.Deferred):
            object.addCallbacks(
                self.serialize,
                lambda x: x,
                callbackKeywords={
                    "perspective": perspective,
                    "method": method,
                    "args": args,
                    "kw": kw,
                },
            )
            return object

        # XXX This call is NOT REENTRANT and testing for reentrancy is just
        # crazy, so it likely won't be.  Don't ever write methods that call the
        # broker's serialize() method recursively (e.g. sending a method call
        # from within a getState (this causes concurrency problems anyway so
        # you really, really shouldn't do it))

        self.serializingPerspective = perspective
        self.jellyMethod = method
        self.jellyArgs = args
        self.jellyKw = kw
        try:
            return jelly(object, self.security, None, self)
        finally:
            self.serializingPerspective = None
            self.jellyMethod = None
            self.jellyArgs = None
            self.jellyKw = None

    def unserialize(self, sexp, perspective=None):
        """
        Unjelly an sexp according to the local security rules for this broker.

        @param sexp: The object to unjelly.
        @param perspective: The perspective.
        """

        self.unserializingPerspective = perspective
        try:
            return unjelly(sexp, self.security, None, self)
        finally:
            self.unserializingPerspective = None

    def newLocalID(self):
        """

        @return: A newly generated LUID.
        """
        self.currentLocalID = self.currentLocalID + 1
        return self.currentLocalID

    def newRequestID(self):
        """

        @return: A newly generated request ID.
        """
        self.currentRequestID = self.currentRequestID + 1
        return self.currentRequestID

    def _sendMessage(self, prefix, perspective, objectID, message, args, kw):
        pbc = None
        pbe = None
        answerRequired = 1
        if "pbcallback" in kw:
            pbc = kw["pbcallback"]
            del kw["pbcallback"]
        if "pberrback" in kw:
            pbe = kw["pberrback"]
            del kw["pberrback"]
        if "pbanswer" in kw:
            assert (not pbe) and (not pbc), "You can't specify a no-answer requirement."
            answerRequired = kw["pbanswer"]
            del kw["pbanswer"]
        if self.disconnected:
            raise DeadReferenceError("Calling Stale Broker")
        try:
            netArgs = self.serialize(args, perspective=perspective, method=message)
            netKw = self.serialize(kw, perspective=perspective, method=message)
        except BaseException:
            return defer.fail(failure.Failure())
        requestID = self.newRequestID()
        if answerRequired:
            rval = defer.Deferred()
            self.waitingForAnswers[requestID] = rval
            if pbc or pbe:
                log.msg('warning! using deprecated "pbcallback"')
                rval.addCallbacks(pbc, pbe)
        else:
            rval = None
        self.sendCall(
            prefix + b"message",
            requestID,
            objectID,
            message,
            answerRequired,
            netArgs,
            netKw,
        )
        return rval

    def proto_message(
        self, requestID, objectID, message, answerRequired, netArgs, netKw
    ):
        self._recvMessage(
            self.localObjectForID,
            requestID,
            objectID,
            message,
            answerRequired,
            netArgs,
            netKw,
        )

    def proto_cachemessage(
        self, requestID, objectID, message, answerRequired, netArgs, netKw
    ):
        self._recvMessage(
            self.cachedLocallyAs,
            requestID,
            objectID,
            message,
            answerRequired,
            netArgs,
            netKw,
        )

    def _recvMessage(
        self,
        findObjMethod,
        requestID,
        objectID,
        message,
        answerRequired,
        netArgs,
        netKw,
    ):
        """
        Received a message-send.

        Look up message based on object, unserialize the arguments, and
        invoke it with args, and send an 'answer' or 'error' response.

        @param findObjMethod: A callable which takes C{objectID} as argument.
        @param requestID: The requiest ID.
        @param objectID: The object ID.
        @param message: The message.
        @param answerRequired:
        @param netArgs: Arguments.
        @param netKw: Keyword arguments.
        """
        if not isinstance(message, str):
            message = message.decode("utf8")

        try:
            object = findObjMethod(objectID)
            if object is None:
                raise Error("Invalid Object ID")
            netResult = object.remoteMessageReceived(self, message, netArgs, netKw)
        except Error as e:
            if answerRequired:
                # If the error is Jellyable or explicitly allowed via our
                # security options, send it back and let the code on the
                # other end deal with unjellying.  If it isn't Jellyable,
                # wrap it in a CopyableFailure, which ensures it can be
                # unjellied on the other end.  We have to do this because
                # all errors must be sent back.
                if isinstance(e, Jellyable) or self.security.isClassAllowed(
                    e.__class__
                ):
                    self._sendError(e, requestID)
                else:
                    self._sendError(CopyableFailure(e), requestID)
        except BaseException:
            if answerRequired:
                log.msg("Peer will receive following PB traceback:", isError=True)
                f = CopyableFailure()
                self._sendError(f, requestID)
            log.err()
        else:
            if answerRequired:
                if isinstance(netResult, defer.Deferred):
                    args = (requestID,)
                    netResult.addCallbacks(
                        self._sendAnswer,
                        self._sendFailureOrError,
                        callbackArgs=args,
                        errbackArgs=args,
                    )
                    # XXX Should this be done somewhere else?
                else:
                    self._sendAnswer(netResult, requestID)

    def _sendAnswer(self, netResult, requestID):
        """
        (internal) Send an answer to a previously sent message.

        @param netResult: The answer.
        @param requestID: The request ID.
        """
        self.sendCall(b"answer", requestID, netResult)

    def proto_answer(self, requestID, netResult):
        """
        (internal) Got an answer to a previously sent message.

        Look up the appropriate callback and call it.

        @param requestID: The request ID.
        @param netResult: The answer.
        """
        d = self.waitingForAnswers[requestID]
        del self.waitingForAnswers[requestID]
        d.callback(self.unserialize(netResult))

    def _sendFailureOrError(self, fail, requestID):
        """
        Call L{_sendError} or L{_sendFailure}, depending on whether C{fail}
        represents an L{Error} subclass or not.

        @param fail: The failure.
        @param requestID: The request ID.
        """
        if fail.check(Error) is None:
            self._sendFailure(fail, requestID)
        else:
            self._sendError(fail, requestID)

    def _sendFailure(self, fail, requestID):
        """
        Log error and then send it.

        @param fail: The failure.
        @param requestID: The request ID.
        """
        log.msg("Peer will receive following PB traceback:")
        log.err(fail)
        self._sendError(fail, requestID)

    def _sendError(self, fail, requestID):
        """
        (internal) Send an error for a previously sent message.

        @param fail: The failure.
        @param requestID: The request ID.
        """
        if isinstance(fail, failure.Failure):
            # If the failures value is jellyable or allowed through security,
            # send the value
            if isinstance(fail.value, Jellyable) or self.security.isClassAllowed(
                fail.value.__class__
            ):
                fail = fail.value
            elif not isinstance(fail, CopyableFailure):
                fail = failure2Copyable(fail, self.factory.unsafeTracebacks)
        if isinstance(fail, CopyableFailure):
            fail.unsafeTracebacks = self.factory.unsafeTracebacks
        self.sendCall(b"error", requestID, self.serialize(fail))

    def proto_error(self, requestID, fail):
        """
        (internal) Deal with an error.

        @param requestID: The request ID.
        @param fail: The failure.
        """
        d = self.waitingForAnswers[requestID]
        del self.waitingForAnswers[requestID]
        d.errback(self.unserialize(fail))

    def sendDecRef(self, objectID):
        """
        (internal) Send a DECREF directive.

        @param objectID: The object ID.
        """
        self.sendCall(b"decref", objectID)

    def proto_decref(self, objectID):
        """
        (internal) Decrement the reference count of an object.

        If the reference count is zero, it will free the reference to this
        object.

        @param objectID: The object ID.
        """
        if isinstance(objectID, str):
            objectID = objectID.encode("utf8")
        refs = self.localObjects[objectID].decref()
        if refs == 0:
            puid = self.localObjects[objectID].object.processUniqueID()
            del self.luids[puid]
            del self.localObjects[objectID]
            self._localCleanup.pop(puid, lambda: None)()

    def decCacheRef(self, objectID):
        """
        (internal) Send a DECACHE directive.

        @param objectID: The object ID.
        """
        self.sendCall(b"decache", objectID)

    def proto_decache(self, objectID):
        """
        (internal) Decrement the reference count of a cached object.

        If the reference count is zero, free the reference, then send an
        'uncached' directive.

        @param objectID: The object ID.
        """
        refs = self.remotelyCachedObjects[objectID].decref()
        # log.msg('decaching: %s #refs: %s' % (objectID, refs))
        if refs == 0:
            lobj = self.remotelyCachedObjects[objectID]
            cacheable = lobj.object
            perspective = lobj.perspective
            # TODO: force_decache needs to be able to force-invalidate a
            # cacheable reference.
            try:
                cacheable.stoppedObserving(
                    perspective, RemoteCacheObserver(self, cacheable, perspective)
                )
            except BaseException:
                log.deferr()
            puid = cacheable.processUniqueID()
            del self.remotelyCachedLUIDs[puid]
            del self.remotelyCachedObjects[objectID]
            self.sendCall(b"uncache", objectID)

    def proto_uncache(self, objectID):
        """
        (internal) Tell the client it is now OK to uncache an object.

        @param objectID: The object ID.
        """
        # log.msg("uncaching locally %d" % objectID)
        obj = self.locallyCachedObjects[objectID]
        obj.broker = None
        ##         def reallyDel(obj=obj):
        ##             obj.__really_del__()
        ##         obj.__del__ = reallyDel
        del self.locallyCachedObjects[objectID]


def respond(challenge, password):
    """
    Respond to a challenge.

    This is useful for challenge/response authentication.

    @param challenge: A challenge.
    @param password: A password.
    @return: The password hashed twice.
    """
    m = md5()
    m.update(password)
    hashedPassword = m.digest()
    m = md5()
    m.update(hashedPassword)
    m.update(challenge)
    doubleHashedPassword = m.digest()
    return doubleHashedPassword


def challenge():
    """

    @return: Some random data.
    """
    crap = bytes(random.randint(65, 90) for x in range(random.randrange(15, 25)))
    crap = md5(crap).digest()
    return crap


class PBClientFactory(protocol.ClientFactory):
    """
    Client factory for PB brokers.

    As with all client factories, use with reactor.connectTCP/SSL/etc..
    getPerspective and getRootObject can be called either before or
    after the connect.
    """

    protocol = Broker
    unsafeTracebacks = False

    def __init__(self, unsafeTracebacks=False, security=globalSecurity):
        """
        @param unsafeTracebacks: if set, tracebacks for exceptions will be sent
            over the wire.
        @type unsafeTracebacks: C{bool}

        @param security: security options used by the broker, default to
            C{globalSecurity}.
        @type security: L{twisted.spread.jelly.SecurityOptions}
        """
        self.unsafeTracebacks = unsafeTracebacks
        self.security = security
        self._reset()

    def buildProtocol(self, addr):
        """
        Build the broker instance, passing the security options to it.
        """
        p = self.protocol(isClient=True, security=self.security)
        p.factory = self
        return p

    def _reset(self):
        self.rootObjectRequests = []  # list of deferred
        self._broker = None
        self._root = None

    def _failAll(self, reason):
        deferreds = self.rootObjectRequests
        self._reset()
        for d in deferreds:
            d.errback(reason)

    def clientConnectionFailed(self, connector, reason):
        self._failAll(reason)

    def clientConnectionLost(self, connector, reason, reconnecting=0):
        """
        Reconnecting subclasses should call with reconnecting=1.
        """
        if reconnecting:
            # Any pending requests will go to next connection attempt
            # so we don't fail them.
            self._broker = None
            self._root = None
        else:
            self._failAll(reason)

    def clientConnectionMade(self, broker):
        self._broker = broker
        self._root = broker.remoteForName("root")
        ds = self.rootObjectRequests
        self.rootObjectRequests = []
        for d in ds:
            d.callback(self._root)

    def getRootObject(self):
        """
        Get root object of remote PB server.

        @return: Deferred of the root object.
        """
        if self._broker and not self._broker.disconnected:
            return defer.succeed(self._root)
        d = defer.Deferred()
        self.rootObjectRequests.append(d)
        return d

    def disconnect(self):
        """
        If the factory is connected, close the connection.

        Note that if you set up the factory to reconnect, you will need to
        implement extra logic to prevent automatic reconnection after this
        is called.
        """
        if self._broker:
            self._broker.transport.loseConnection()

    def _cbSendUsername(self, root, username, password, client):
        return root.callRemote("login", username).addCallback(
            self._cbResponse, password, client
        )

    def _cbResponse(self, challenges, password, client):
        challenge, challenger = challenges
        return challenger.callRemote("respond", respond(challenge, password), client)

    def _cbLoginAnonymous(self, root, client):
        """
        Attempt an anonymous login on the given remote root object.

        @type root: L{RemoteReference}
        @param root: The object on which to attempt the login, most likely
            returned by a call to L{PBClientFactory.getRootObject}.

        @param client: A jellyable object which will be used as the I{mind}
            parameter for the login attempt.

        @rtype: L{Deferred}
        @return: A L{Deferred} which will be called back with a
            L{RemoteReference} to an avatar when anonymous login succeeds, or
            which will errback if anonymous login fails.
        """
        return root.callRemote("loginAnonymous", client)

    def login(self, credentials, client=None):
        """
        Login and get perspective from remote PB server.

        Currently the following credentials are supported::

            L{twisted.cred.credentials.IUsernamePassword}
            L{twisted.cred.credentials.IAnonymous}

        @rtype: L{Deferred}
        @return: A L{Deferred} which will be called back with a
            L{RemoteReference} for the avatar logged in to, or which will
            errback if login fails.
        """
        d = self.getRootObject()

        if IAnonymous.providedBy(credentials):
            d.addCallback(self._cbLoginAnonymous, client)
        else:
            d.addCallback(
                self._cbSendUsername, credentials.username, credentials.password, client
            )
        return d


class PBServerFactory(protocol.ServerFactory):
    """
    Server factory for perspective broker.

    Login is done using a Portal object, whose realm is expected to return
    avatars implementing IPerspective. The credential checkers in the portal
    should accept IUsernameHashedPassword or IUsernameMD5Password.

    Alternatively, any object providing or adaptable to L{IPBRoot} can be
    used instead of a portal to provide the root object of the PB server.
    """

    unsafeTracebacks = False

    # object broker factory
    protocol = Broker

    def __init__(self, root, unsafeTracebacks=False, security=globalSecurity):
        """
        @param root: factory providing the root Referenceable used by the broker.
        @type root: object providing or adaptable to L{IPBRoot}.

        @param unsafeTracebacks: if set, tracebacks for exceptions will be sent
            over the wire.
        @type unsafeTracebacks: C{bool}

        @param security: security options used by the broker, default to
            C{globalSecurity}.
        @type security: L{twisted.spread.jelly.SecurityOptions}
        """
        self.root = IPBRoot(root)
        self.unsafeTracebacks = unsafeTracebacks
        self.security = security

    def buildProtocol(self, addr):
        """
        Return a Broker attached to the factory (as the service provider).
        """
        proto = self.protocol(isClient=False, security=self.security)
        proto.factory = self
        proto.setNameForLocal("root", self.root.rootObject(proto))
        return proto

    def clientConnectionMade(self, protocol):
        # XXX does this method make any sense?
        pass


class IUsernameMD5Password(ICredentials):
    """
    I encapsulate a username and a hashed password.

    This credential is used for username/password over PB. CredentialCheckers
    which check this kind of credential must store the passwords in plaintext
    form or as a MD5 digest.

    @type username: C{str} or C{Deferred}
    @ivar username: The username associated with these credentials.
    """

    def checkPassword(password):
        """
        Validate these credentials against the correct password.

        @type password: C{str}
        @param password: The correct, plaintext password against which to
            check.

        @rtype: C{bool} or L{Deferred}
        @return: C{True} if the credentials represented by this object match the
            given password, C{False} if they do not, or a L{Deferred} which will
            be called back with one of these values.
        """

    def checkMD5Password(password):
        """
        Validate these credentials against the correct MD5 digest of the
        password.

        @type password: C{str}
        @param password: The correct MD5 digest of a password against which to
            check.

        @rtype: C{bool} or L{Deferred}
        @return: C{True} if the credentials represented by this object match the
            given digest, C{False} if they do not, or a L{Deferred} which will
            be called back with one of these values.
        """


@implementer(IPBRoot)
class _PortalRoot:
    """
    Root object, used to login to portal.
    """

    def __init__(self, portal):
        self.portal = portal

    def rootObject(self, broker):
        return _PortalWrapper(self.portal, broker)


registerAdapter(_PortalRoot, Portal, IPBRoot)


class _JellyableAvatarMixin:
    """
    Helper class for code which deals with avatars which PB must be capable of
    sending to a peer.
    """

    def _cbLogin(self, result):
        """
        Ensure that the avatar to be returned to the client is jellyable and
        set up disconnection notification to call the realm's logout object.
        """
        (interface, avatar, logout) = result
        if not IJellyable.providedBy(avatar):
            avatar = AsReferenceable(avatar, "perspective")

        puid = avatar.processUniqueID()

        # only call logout once, whether the connection is dropped (disconnect)
        # or a logout occurs (cleanup), and be careful to drop the reference to
        # it in either case
        logout = [logout]

        def maybeLogout():
            if not logout:
                return
            fn = logout[0]
            del logout[0]
            fn()

        self.broker._localCleanup[puid] = maybeLogout
        self.broker.notifyOnDisconnect(maybeLogout)

        return avatar


class _PortalWrapper(Referenceable, _JellyableAvatarMixin):
    """
    Root Referenceable object, used to login to portal.
    """

    def __init__(self, portal, broker):
        self.portal = portal
        self.broker = broker

    def remote_login(self, username):
        """
        Start of username/password login.

        @param username: The username.
        """
        c = challenge()
        return c, _PortalAuthChallenger(self.portal, self.broker, username, c)

    def remote_loginAnonymous(self, mind):
        """
        Attempt an anonymous login.

        @param mind: An object to use as the mind parameter to the portal login
            call (possibly None).

        @rtype: L{Deferred}
        @return: A Deferred which will be called back with an avatar when login
            succeeds or which will be errbacked if login fails somehow.
        """
        d = self.portal.login(Anonymous(), mind, IPerspective)
        d.addCallback(self._cbLogin)
        return d


@implementer(IUsernameHashedPassword, IUsernameMD5Password)
class _PortalAuthChallenger(Referenceable, _JellyableAvatarMixin):
    """
    Called with response to password challenge.
    """

    def __init__(self, portal, broker, username, challenge):
        self.portal = portal
        self.broker = broker
        self.username = username
        self.challenge = challenge

    def remote_respond(self, response, mind):
        self.response = response
        d = self.portal.login(self, mind, IPerspective)
        d.addCallback(self._cbLogin)
        return d

    def checkPassword(self, password):
        """
        L{IUsernameHashedPassword}

        @param password: The password.
        @return: L{_PortalAuthChallenger.checkMD5Password}
        """
        return self.checkMD5Password(md5(password).digest())

    def checkMD5Password(self, md5Password):
        """
        L{IUsernameMD5Password}

        @param md5Password:
        @rtype: L{bool}
        @return: L{True} if password matches.
        """
        md = md5()
        md.update(md5Password)
        md.update(self.challenge)
        correct = md.digest()
        return self.response == correct


__all__ = [
    # Everything from flavors is exposed publicly here.
    "IPBRoot",
    "Serializable",
    "Referenceable",
    "NoSuchMethod",
    "Root",
    "ViewPoint",
    "Viewable",
    "Copyable",
    "Jellyable",
    "Cacheable",
    "RemoteCopy",
    "RemoteCache",
    "RemoteCacheObserver",
    "copyTags",
    "setUnjellyableForClass",
    "setUnjellyableFactoryForClass",
    "setUnjellyableForClassTree",
    "setCopierForClass",
    "setFactoryForClass",
    "setCopierForClassTree",
    "MAX_BROKER_REFS",
    "portno",
    "ProtocolError",
    "DeadReferenceError",
    "Error",
    "PBConnectionLost",
    "RemoteMethod",
    "IPerspective",
    "Avatar",
    "AsReferenceable",
    "RemoteReference",
    "CopyableFailure",
    "CopiedFailure",
    "failure2Copyable",
    "Broker",
    "respond",
    "challenge",
    "PBClientFactory",
    "PBServerFactory",
    "IUsernameMD5Password",
]

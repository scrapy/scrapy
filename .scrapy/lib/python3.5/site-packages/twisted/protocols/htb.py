# -*- test-case-name: twisted.test.test_htb -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Hierarchical Token Bucket traffic shaping.

Patterned after U{Martin Devera's Hierarchical Token Bucket traffic
shaper for the Linux kernel<http://luxik.cdi.cz/~devik/qos/htb/>}.

@seealso: U{HTB Linux queuing discipline manual - user guide
  <http://luxik.cdi.cz/~devik/qos/htb/manual/userg.htm>}
@seealso: U{Token Bucket Filter in Linux Advanced Routing & Traffic Control
    HOWTO<http://lartc.org/howto/lartc.qdisc.classless.html#AEN682>}
"""


# TODO: Investigate whether we should be using os.times()[-1] instead of
# time.time.  time.time, it has been pointed out, can go backwards.  Is
# the same true of os.times?
from time import time
from zope.interface import implementer, Interface

from twisted.protocols import pcp


class Bucket:
    """
    Implementation of a Token bucket.

    A bucket can hold a certain number of tokens and it drains over time.

    @cvar maxburst: The maximum number of tokens that the bucket can
        hold at any given time. If this is L{None}, the bucket has
        an infinite size.
    @type maxburst: C{int}
    @cvar rate: The rate at which the bucket drains, in number
        of tokens per second. If the rate is L{None}, the bucket
        drains instantaneously.
    @type rate: C{int}
    """

    maxburst = None
    rate = None

    _refcount = 0

    def __init__(self, parentBucket=None):
        """
        Create a L{Bucket} that may have a parent L{Bucket}.

        @param parentBucket: If a parent Bucket is specified,
            all L{add} and L{drip} operations on this L{Bucket}
            will be applied on the parent L{Bucket} as well.
        @type parentBucket: L{Bucket}
        """
        self.content = 0
        self.parentBucket = parentBucket
        self.lastDrip = time()


    def add(self, amount):
        """
        Adds tokens to the L{Bucket} and its C{parentBucket}.

        This will add as many of the C{amount} tokens as will fit into both
        this L{Bucket} and its C{parentBucket}.

        @param amount: The number of tokens to try to add.
        @type amount: C{int}

        @returns: The number of tokens that actually fit.
        @returntype: C{int}
        """
        self.drip()
        if self.maxburst is None:
            allowable = amount
        else:
            allowable = min(amount, self.maxburst - self.content)

        if self.parentBucket is not None:
            allowable = self.parentBucket.add(allowable)
        self.content += allowable
        return allowable


    def drip(self):
        """
        Let some of the bucket drain.

        The L{Bucket} drains at the rate specified by the class
        variable C{rate}.

        @returns: C{True} if the bucket is empty after this drip.
        @returntype: C{bool}
        """
        if self.parentBucket is not None:
            self.parentBucket.drip()

        if self.rate is None:
            self.content = 0
        else:
            now = time()
            deltaTime = now - self.lastDrip
            deltaTokens = deltaTime * self.rate
            self.content = max(0, self.content - deltaTokens)
            self.lastDrip = now
        return self.content == 0


class IBucketFilter(Interface):
    def getBucketFor(*somethings, **some_kw):
        """
        Return a L{Bucket} corresponding to the provided parameters.

        @returntype: L{Bucket}
        """

@implementer(IBucketFilter)
class HierarchicalBucketFilter:
    """
    Filter things into buckets that can be nested.

    @cvar bucketFactory: Class of buckets to make.
    @type bucketFactory: L{Bucket}
    @cvar sweepInterval: Seconds between sweeping out the bucket cache.
    @type sweepInterval: C{int}
    """
    bucketFactory = Bucket
    sweepInterval = None

    def __init__(self, parentFilter=None):
        self.buckets = {}
        self.parentFilter = parentFilter
        self.lastSweep = time()

    def getBucketFor(self, *a, **kw):
        """
        Find or create a L{Bucket} corresponding to the provided parameters.

        Any parameters are passed on to L{getBucketKey}, from them it
        decides which bucket you get.

        @returntype: L{Bucket}
        """
        if ((self.sweepInterval is not None)
            and ((time() - self.lastSweep) > self.sweepInterval)):
            self.sweep()

        if self.parentFilter:
            parentBucket = self.parentFilter.getBucketFor(self, *a, **kw)
        else:
            parentBucket = None

        key = self.getBucketKey(*a, **kw)
        bucket = self.buckets.get(key)
        if bucket is None:
            bucket = self.bucketFactory(parentBucket)
            self.buckets[key] = bucket
        return bucket

    def getBucketKey(self, *a, **kw):
        """
        Construct a key based on the input parameters to choose a L{Bucket}.

        The default implementation returns the same key for all
        arguments. Override this method to provide L{Bucket} selection.

        @returns: Something to be used as a key in the bucket cache.
        """
        return None

    def sweep(self):
        """
        Remove empty buckets.
        """
        for key, bucket in self.buckets.items():
            bucket_is_empty = bucket.drip()
            if (bucket._refcount == 0) and bucket_is_empty:
                del self.buckets[key]

        self.lastSweep = time()


class FilterByHost(HierarchicalBucketFilter):
    """
    A Hierarchical Bucket filter with a L{Bucket} for each host.
    """
    sweepInterval = 60 * 20

    def getBucketKey(self, transport):
        return transport.getPeer()[1]


class FilterByServer(HierarchicalBucketFilter):
    """
    A Hierarchical Bucket filter with a L{Bucket} for each service.
    """
    sweepInterval = None

    def getBucketKey(self, transport):
        return transport.getHost()[2]


class ShapedConsumer(pcp.ProducerConsumerProxy):
    """
    Wraps a C{Consumer} and shapes the rate at which it receives data.
    """
    # Providing a Pull interface means I don't have to try to schedule
    # traffic with callLaters.
    iAmStreaming = False

    def __init__(self, consumer, bucket):
        pcp.ProducerConsumerProxy.__init__(self, consumer)
        self.bucket = bucket
        self.bucket._refcount += 1

    def _writeSomeData(self, data):
        # In practice, this actually results in obscene amounts of
        # overhead, as a result of generating lots and lots of packets
        # with twelve-byte payloads.  We may need to do a version of
        # this with scheduled writes after all.
        amount = self.bucket.add(len(data))
        return pcp.ProducerConsumerProxy._writeSomeData(self, data[:amount])

    def stopProducing(self):
        pcp.ProducerConsumerProxy.stopProducing(self)
        self.bucket._refcount -= 1


class ShapedTransport(ShapedConsumer):
    """
    Wraps a C{Transport} and shapes the rate at which it receives data.

    This is a L{ShapedConsumer} with a little bit of magic to provide for
    the case where the consumer it wraps is also a C{Transport} and people
    will be attempting to access attributes this does not proxy as a
    C{Consumer} (e.g. C{loseConnection}).
    """
    # Ugh.  We only wanted to filter IConsumer, not ITransport.

    iAmStreaming = False
    def __getattr__(self, name):
        # Because people will be doing things like .getPeer and
        # .loseConnection on me.
        return getattr(self.consumer, name)


class ShapedProtocolFactory:
    """
    Dispense C{Protocols} with traffic shaping on their transports.

    Usage::

        myserver = SomeFactory()
        myserver.protocol = ShapedProtocolFactory(myserver.protocol,
                                                  bucketFilter)

    Where C{SomeServerFactory} is a L{twisted.internet.protocol.Factory}, and
    C{bucketFilter} is an instance of L{HierarchicalBucketFilter}.
    """
    def __init__(self, protoClass, bucketFilter):
        """
        Tell me what to wrap and where to get buckets.

        @param protoClass: The class of C{Protocol} this will generate
          wrapped instances of.
        @type protoClass: L{Protocol<twisted.internet.interfaces.IProtocol>}
          class
        @param bucketFilter: The filter which will determine how
          traffic is shaped.
        @type bucketFilter: L{HierarchicalBucketFilter}.
        """
        # More precisely, protoClass can be any callable that will return
        # instances of something that implements IProtocol.
        self.protocol = protoClass
        self.bucketFilter = bucketFilter

    def __call__(self, *a, **kw):
        """
        Make a C{Protocol} instance with a shaped transport.

        Any parameters will be passed on to the protocol's initializer.

        @returns: A C{Protocol} instance with a L{ShapedTransport}.
        """
        proto = self.protocol(*a, **kw)
        origMakeConnection = proto.makeConnection
        def makeConnection(transport):
            bucket = self.bucketFilter.getBucketFor(transport)
            shapedTransport = ShapedTransport(transport, bucket)
            return origMakeConnection(shapedTransport)
        proto.makeConnection = makeConnection
        return proto

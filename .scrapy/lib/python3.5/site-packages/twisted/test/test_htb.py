# -*- Python -*-

__version__ = '$Revision: 1.3 $'[11:-2]

from twisted.trial import unittest
from twisted.protocols import htb
from .test_pcp import DummyConsumer

class DummyClock:
    time = 0
    def set(self, when):
        self.time = when

    def __call__(self):
        return self.time



class SomeBucket(htb.Bucket):
    maxburst = 100
    rate = 2



class TestBucketBase(unittest.TestCase):
    def setUp(self):
        self._realTimeFunc = htb.time
        self.clock = DummyClock()
        htb.time = self.clock

    def tearDown(self):
        htb.time = self._realTimeFunc



class BucketTests(TestBucketBase):
    def testBucketSize(self):
        """
        Testing the size of the bucket.
        """
        b = SomeBucket()
        fit = b.add(1000)
        self.assertEqual(100, fit)


    def testBucketDrain(self):
        """
        Testing the bucket's drain rate.
        """
        b = SomeBucket()
        fit = b.add(1000)
        self.clock.set(10)
        fit = b.add(1000)
        self.assertEqual(20, fit)


    def test_bucketEmpty(self):
        """
        L{htb.Bucket.drip} returns C{True} if the bucket is empty after that drip.
        """
        b = SomeBucket()
        b.add(20)
        self.clock.set(9)
        empty = b.drip()
        self.assertFalse(empty)
        self.clock.set(10)
        empty = b.drip()
        self.assertTrue(empty)



class BucketNestingTests(TestBucketBase):
    def setUp(self):
        TestBucketBase.setUp(self)
        self.parent = SomeBucket()
        self.child1 = SomeBucket(self.parent)
        self.child2 = SomeBucket(self.parent)


    def testBucketParentSize(self):
        # Use up most of the parent bucket.
        self.child1.add(90)
        fit = self.child2.add(90)
        self.assertEqual(10, fit)


    def testBucketParentRate(self):
        # Make the parent bucket drain slower.
        self.parent.rate = 1
        # Fill both child1 and parent.
        self.child1.add(100)
        self.clock.set(10)
        fit = self.child1.add(100)
        # How much room was there?  The child bucket would have had 20,
        # but the parent bucket only ten (so no, it wouldn't make too much
        # sense to have a child bucket draining faster than its parent in a real
        # application.)
        self.assertEqual(10, fit)


# TODO: Test the Transport stuff?

class ConsumerShaperTests(TestBucketBase):
    def setUp(self):
        TestBucketBase.setUp(self)
        self.underlying = DummyConsumer()
        self.bucket = SomeBucket()
        self.shaped = htb.ShapedConsumer(self.underlying, self.bucket)


    def testRate(self):
        # Start off with a full bucket, so the burst-size doesn't factor in
        # to the calculations.
        delta_t = 10
        self.bucket.add(100)
        self.shaped.write("x" * 100)
        self.clock.set(delta_t)
        self.shaped.resumeProducing()
        self.assertEqual(len(self.underlying.getvalue()),
                             delta_t * self.bucket.rate)


    def testBucketRefs(self):
        self.assertEqual(self.bucket._refcount, 1)
        self.shaped.stopProducing()
        self.assertEqual(self.bucket._refcount, 0)

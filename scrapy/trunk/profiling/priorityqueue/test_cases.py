import sys
import unittest
from pq_classes import PriorityQueue1, PriorityQueue2, PriorityQueue3, PriorityQueue4, PriorityQueue5, PriorityQueue6
from pq_classes import *

# (ITEM, PRIORITY)
INPUT = [(1, -5), (30, -1), (80, -3), (4, 1), (6, 3), (20, 0), (50, -1)]
OUTPUT = [(1, -5), (80, -3), (30, -1), (50, -1), (20, 0), (4, 1), (6, 3)]

PRIOSIZE = reduce(max, (abs(i[1]) for i in INPUT + OUTPUT)) * 2

class TestPriorityQueue(object):

    def test_popping(self):
        pq = self.PriorityQueue(PRIOSIZE)
        for item, pr in INPUT:
            pq.push(item, pr)
        l = []
        while pq:
            l.append(pq.pop())
        self.assertEquals(l, OUTPUT)

    def test_iter(self):
        pq = self.PriorityQueue(PRIOSIZE)
        for item, pr in INPUT:
            pq.push(item, pr)
        result = [x for x in pq]
        self.assertEquals(result, OUTPUT)

    def test_nonzero(self):
        pq = self.PriorityQueue(PRIOSIZE)
        pq.push(80, -1)
        pq.push(20, 0)
        pq.push(30, 1)

        pq.pop()
        self.assertEquals(bool(pq), True)
        pq.pop()
        self.assertEquals(bool(pq), True)
        pq.pop()
        self.assertEquals(bool(pq), False)

    def test_len(self):
        pq = self.PriorityQueue(PRIOSIZE)
        pq.push(80, -1)
        pq.push(20, 0)
        pq.push(30, 1)

        self.assertEquals(len(pq), 3)
        pq.pop()
        self.assertEquals(len(pq), 2)
        pq.pop()
        self.assertEquals(len(pq), 1)
        pq.pop()
        self.assertEquals(len(pq), 0)

    def test_indexerror(self):
        pq = self.PriorityQueue(PRIOSIZE)
        self.assertRaises(IndexError, pq.pop)


# automatically test any PriorityQueueN class defined at pq_classes
prioclasses = [(name, cls) for name, cls in globals().items() if name.startswith('PriorityQueue')]
for name, cls in prioclasses:
    testname = '%sTestCase' % name
    testcase = type(testname, (TestPriorityQueue, unittest.TestCase), {'PriorityQueue': cls})
    setattr(sys.modules[__name__], testname, testcase)


if __name__ == '__main__':
    print "\n== Unit testing for every implementation =="
    unittest.main()

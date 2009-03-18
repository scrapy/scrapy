import unittest

from scrapy.utils.datatypes import PriorityQueue, PriorityStack

# (ITEM, PRIORITY)
INPUT = [(1, -5), (30, -1), (80, -3), (4, 1), (6, 3), (20, 0), (50, -1)]

class PriorityQueueTestCase(unittest.TestCase):

    output = [(1, -5), (80, -3), (30, -1), (50, -1), (20, 0), (4, 1), (6, 3)]

    def test_popping(self):
        pq = PriorityQueue()
        for item, pr in INPUT:
            pq.push(item, pr)
        l = []
        while pq:
            l.append(pq.pop())
        self.assertEquals(l, self.output)

    def test_iter(self):
        pq = PriorityQueue()
        for item, pr in INPUT:
            pq.push(item, pr)
        result = [x for x in pq]
        self.assertEquals(result, self.output) 
    
    def test_nonzero(self):
        pq = PriorityQueue()
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
        pq = PriorityQueue()
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

class PriorityStackTestCase(unittest.TestCase):

    output = [(1, -5), (80, -3), (50, -1), (30, -1), (20, 0), (4, 1), (6, 3)]

    def test_popping(self):
        pq = PriorityStack()
        for item, pr in INPUT:
            pq.push(item, pr)
        l = []
        while pq:
            l.append(pq.pop())
        self.assertEquals(l, self.output)

    def test_iter(self):
        pq = PriorityStack()
        for item, pr in INPUT:
            pq.push(item, pr)
        result = [x for x in pq]
        self.assertEquals(result, self.output) 
    
if __name__ == "__main__":
    unittest.main()

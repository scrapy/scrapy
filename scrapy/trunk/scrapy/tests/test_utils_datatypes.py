import unittest
from scrapy.utils.datatypes import PriorityQueue

class DatatypesTestCase(unittest.TestCase):

    def test_priority_queue(self):
        pq = PriorityQueue()

        pq.put('b', priority=1)
        pq.put('a', priority=1)
        pq.put('c', priority=1)
        pq.put('z', priority=0)
        pq.put('d', priority=2)

        v = []
        p = []
        while not pq.empty():
            priority, value = pq.get()
            v.append(value)
            p.append(priority)

        self.assertEqual(v, ['z', 'b', 'a', 'c', 'd'])
        self.assertEqual(p, [0, 1, 1, 1, 2])

if __name__ == "__main__":
    unittest.main()

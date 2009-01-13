import unittest

from scrapy.utils.datatypes import PriorityQueue, PriorityStack

class DatatypesTestCase(unittest.TestCase):

    def test_priority_queue(self):

        input = [('five', 5), ('three-1', 3), ('three-2', 3), ('six', 6), ('one', 1)]
        output = [('one', 1), ('three-1', 3), ('three-2', 3), ('five', 5), ('six', 6)]

        pq = PriorityQueue()
        assert not bool(pq)
        for item, prio in input:
            pq.push(item, prio)
        out = []
        assert bool(pq)
        self.assertEqual(len(pq), len(input))
        while pq:
            out.append(pq.pop())
        self.assertEqual(len(pq), 0)
        self.assertEqual(out, output)

    def test_priority_stack(self):

        input = [('five', 5), ('three-1', 3), ('three-2', 3), ('six', 6), ('one', 1)]
        output = [('one', 1), ('three-2', 3), ('three-1', 3), ('five', 5), ('six', 6)]

        pq = PriorityStack()
        assert not bool(pq)
        for item, prio in input:
            pq.push(item, prio)
        assert bool(pq)
        out = []
        self.assertEqual(len(pq), len(input))
        while pq:
            out.append(pq.pop())
        self.assertEqual(len(pq), 0)
        self.assertEqual(out, output)

if __name__ == "__main__":
    unittest.main()

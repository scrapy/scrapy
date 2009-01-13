import unittest

from scrapy.utils.datatypes import PriorityQueue, PriorityStack

class DatatypesTestCase(unittest.TestCase):

    def test_priority_queue(self):

        input = [('five', 5), ('three-1', 3), ('three-2', 3), ('six', 6), ('one', 1)]
        output = [('one', 1), ('three-1', 3), ('three-2', 3), ('five', 5), ('six', 6)]

        pq = PriorityQueue()
        for item, prio in input:
            pq.push(item, prio)
        out = []
        while pq:
            out.append(pq.pop())
        self.assertEqual(out, output)

    def test_priority_stack(self):

        input = [('five', 5), ('three-1', 3), ('three-2', 3), ('six', 6), ('one', 1)]
        output = [('one', 1), ('three-2', 3), ('three-1', 3), ('five', 5), ('six', 6)]

        pq = PriorityStack()
        for item, prio in input:
            pq.push(item, prio)
        out = []
        while pq:
            out.append(pq.pop())
        self.assertEqual(out, output)

if __name__ == "__main__":
    unittest.main()

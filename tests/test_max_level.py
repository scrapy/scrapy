import unittest
from scrapy.commands import parse

class TestMaxLevel(unittest.TestCase):
    def setUp(self):
        self.command = parse.Command()

    def tearDown(self):
        self.command.write_max_level_coverage_to_file()
        
    def test_max_Lvl_no_items_no_requests(self):
        self.command.items = {}
        self.command.requests = {}
        self.command.max_level #comment out to get 0%
        self.assertEqual(parse.max_level_coverage["run_2"], "hit")
        self.assertEqual(parse.max_level_coverage["run_4"], "hit")

    def test_max_Lvl_with_items_no_request(self):
        self.command.items = {1: "item1", 2: "item2"}
        self.command.requests = {}
        self.command.max_level #comment out to get 0%
        self.assertEqual(parse.max_level_coverage["run_1"], "hit")
        self.assertEqual(parse.max_level_coverage["run_4"], "hit")

    def test_max_Lvl_no_items_with_request(self):
        self.command.items = {}
        self.command.requests = {1: "http://examplerequest.com"}
        self.command.max_level #comment out to get 0%
        self.assertEqual(parse.max_level_coverage["run_2"], "hit")
        self.assertEqual(parse.max_level_coverage["run_3"], "hit")
        
    def test_max_Lvl_with_items_with_request(self):
        self.command.items = {}
        self.command.requests = {1: "http://examplerequest.com", 2: "http://examplerequest.com"}
        self.command.max_level #comment out to get 0%
        self.assertEqual(parse.max_level_coverage["run_1"], "hit")
        self.assertEqual(parse.max_level_coverage["run_3"], "hit")

    if __name__ == '__main__':
        unittest.main()

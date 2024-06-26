import unittest
from scrapy.commands import parse
from scrapy.http import Request
from scrapy.settings import Settings

class TestMaxLevel(unittest.TestCase):
    def setUp(self):
        self.command = parse.Command()
        self.command.settings = Settings()

    def tearDown(self):
        self.command.write_max_level_coverage_to_file()
        
    def test_max_Lvl_no_items_no_requests(self):
        self.command.items = {}
        self.command.requests = {}
        self.assertEqual(self.command.max_level, 0) #runs the function with a unique case
        self.assertEqual(parse.max_level_coverage["run_2"], "hit")
        self.assertEqual(parse.max_level_coverage["run_4"], "hit")

    def test_max_Lvl_with_items_no_request(self):
        self.command.items = {1: ["item1"], 2: ["item2"]}
        self.command.requests = {}
        self.assertEqual(self.command.max_level, 2)
        self.assertEqual(parse.max_level_coverage["run_1"], "hit")
        self.assertEqual(parse.max_level_coverage["run_4"], "hit")

    def test_max_Lvl_no_items_with_request(self):
        self.command.items = {}
        self.command.requests = {1: [Request("http://coverage.com")]}
        self.assertEqual(self.command.max_level, 1) 
        self.assertEqual(parse.max_level_coverage["run_2"], "hit")
        self.assertEqual(parse.max_level_coverage["run_3"], "hit")
        
    def test_max_Lvl_with_items_with_request(self):
        self.command.items = {}
        self.command.requests = {1: [Request("http://coverage.com")], 2: [Request("http://coverage2.com")]}
        self.assertEqual(self.command.max_level, 2)
        self.assertEqual(parse.max_level_coverage["run_1"], "hit")
        self.assertEqual(parse.max_level_coverage["run_3"], "hit")

    if __name__ == '__main__':
        unittest.main()

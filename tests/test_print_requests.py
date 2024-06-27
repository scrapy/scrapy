import unittest

from scrapy.commands import parse

class TestPrintRequests(unittest.TestCase):
    def setUp(self):
        self.command = parse.Command()

    def tearDown(self):
        self.command.write_print_request_coverage_to_file()

    def test_print_requests_no_level_no_request(self):
        self.command.requests = {}
        self.command.print_requests(None, colour=False) 
        self.assertEqual(parse.print_requests_coverage["run_1"], "hit")
        self.assertEqual(parse.print_requests_coverage["run_1.2"], "hit")
    
    def test_print_requests_no_level_with_request(self):
        self.command.requests = {1: "http://examplerequest.com"}
        self.command.print_requests(None, colour=False)
        self.assertEqual(parse.print_requests_coverage["run_1"], "hit")
        self.assertEqual(parse.print_requests_coverage["run_1.1"], "hit")

    # both cases below cover the "main" else clause
    def test_print_requests_with_level_with_request(self):
        self.command.requests = {1: "http://examplerequest.com"}
        self.command.print_requests(1, colour=False)
        self.assertEqual(parse.print_requests_coverage["run_2"], "hit")

    def test_print_requests_with_level_no_request(self):
        self.command.requests = {1: "http://examplerequest.com"}
        self.command.print_requests(2, colour=False) 
        self.assertEqual(parse.print_requests_coverage["run_2"], "hit")

if __name__ == '__main__':
    unittest.main()

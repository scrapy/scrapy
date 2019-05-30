from twisted.trial import unittest
from scrapy.utils.python import to_native_str
from scrapy.extensions.robotstxtparser import PythonRobotParser

class PythonRobotParserTest(unittest.TestCase):
    def test_allowed(self):
        rp = PythonRobotParser(to_native_str("User-agent: * \n"
                                            "Disallow: /disallowed \n"
                                            "Allow: /allowed"))
        self.assertTrue(rp.allowed("https://www.example.com/allowed", "*"))
        self.assertFalse(rp.allowed("https://www.example.com/disallowed", "*"))

    def test_sitemaps(self):
        rp = PythonRobotParser(to_native_str("User-agent: * \n"
                                            "Disallow: /disallowed \n"
                                            "Allow: /allowed"))
        self.assertTrue(rp.sitemaps() is None)

    def test_preferred_host(self):
        rp = PythonRobotParser(to_native_str("User-agent: * \n"
                                            "Disallow: /disallowed \n"
                                            "Allow: /allowed"))
        self.assertTrue(rp.preferred_host() is None)

    def test_crawl_delay(self):
        rp = PythonRobotParser(to_native_str("User-agent: * \n"
                                            "Disallow: /disallowed \n"
                                            "Allow: /allowed \n"
                                            "Crawl-delay: 10"))
        from six.moves.urllib_robotparser import RobotFileParser
        if hasattr(RobotFileParser, "crawl_delay"):
            self.assertTrue(rp.crawl_delay("*") == 10)
        else:
            self.assertTrue(rp.crawl_delay("*") is None)
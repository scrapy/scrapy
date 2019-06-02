from twisted.trial import unittest
from scrapy.utils.python import to_native_str
from scrapy.extensions.robotstxtparser import PythonRobotParser, ReppyRobotParser, RerpRobotParser

class PythonRobotParserTest(unittest.TestCase):
    def test_allowed(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Crawl-delay: 10".encode('utf-8'))
        rp = PythonRobotParser(robotstxt_content)
        self.assertTrue(rp.allowed("https://www.example.com/allowed", "*"))
        self.assertFalse(rp.allowed("https://www.example.com/disallowed", "*"))

    def test_sitemaps(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Crawl-delay: 10".encode('utf-8'))
        rp = PythonRobotParser(robotstxt_content)
        self.assertTrue(not list(rp.sitemaps()))

    def test_preferred_host(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Crawl-delay: 10".encode('utf-8'))
        rp = PythonRobotParser(robotstxt_content)
        self.assertTrue(rp.preferred_host() is None)

    def test_crawl_delay(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Crawl-delay: 10".encode('utf-8'))
        rp = PythonRobotParser(robotstxt_content)
        from six.moves.urllib_robotparser import RobotFileParser
        if hasattr(RobotFileParser, "crawl_delay"):
            self.assertTrue(rp.crawl_delay("*") == 10.0)
        else:
            self.assertTrue(rp.crawl_delay("*") is None)

        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed ".encode('utf-8'))
        rp = PythonRobotParser(robotstxt_content)
        self.assertTrue(rp.crawl_delay('*') is None)

class ReppyRobotParserTest(unittest.TestCase):
    def test_allowed(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Crawl-delay: 10".encode('utf-8'))
        rp = ReppyRobotParser(robotstxt_content)
        self.assertTrue(rp.allowed("https://www.example.com/allowed", "*"))
        self.assertFalse(rp.allowed("https://www.example.com/disallowed", "*"))

    def test_sitemaps(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Sitemap: https://example.com/sitemap.xml".encode('utf-8'))
        rp = ReppyRobotParser(robotstxt_content)
        sitemaps = list(rp.sitemaps())
        self.assertTrue(len(sitemaps) == 1)
        self.assertTrue("https://example.com/sitemap.xml" in sitemaps)

        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed".encode('utf-8'))
        rp = ReppyRobotParser(robotstxt_content)
        self.assertTrue(not list(rp.sitemaps()))

    def test_preferred_host(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Crawl-delay: 10".encode('utf-8'))
        rp = ReppyRobotParser(robotstxt_content)
        self.assertTrue(rp.preferred_host() is None)

    def test_crawl_delay(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Crawl-delay: 10".encode('utf-8'))
        rp = ReppyRobotParser(robotstxt_content)
        self.assertTrue(rp.crawl_delay('*') == 10.0)

        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed".encode('utf-8'))
        rp = ReppyRobotParser(robotstxt_content)
        self.assertTrue(rp.crawl_delay('*') is None)

class RerpRobotParserTest(unittest.TestCase):
    def test_allowed(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Crawl-delay: 10".encode('utf-8'))
        rp = RerpRobotParser(robotstxt_content)
        self.assertTrue(rp.allowed("https://www.example.com/allowed", "*"))
        self.assertFalse(rp.allowed("https://www.example.com/disallowed", "*"))

    def test_sitemaps(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Sitemap: https://example.com/sitemap.xml".encode('utf-8'))
        rp = RerpRobotParser(robotstxt_content)
        sitemaps = list(rp.sitemaps())
        self.assertTrue(len(sitemaps) == 1)
        self.assertTrue("https://example.com/sitemap.xml" in sitemaps)

        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed".encode('utf-8'))
        rp = RerpRobotParser(robotstxt_content)
        self.assertTrue(not list(rp.sitemaps()))

    def test_preferred_host(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Crawl-delay: 10".encode('utf-8'))
        rp = RerpRobotParser(robotstxt_content)
        self.assertTrue(rp.preferred_host() is None)

    def test_crawl_delay(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Crawl-delay: 10".encode('utf-8'))
        rp = RerpRobotParser(robotstxt_content)
        self.assertTrue(rp.crawl_delay('*') == 10.0)

        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed".encode('utf-8'))
        rp = RerpRobotParser(robotstxt_content)
        self.assertTrue(rp.crawl_delay('*') is None)
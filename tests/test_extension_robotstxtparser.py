# coding=utf-8
from twisted.trial import unittest
from scrapy.utils.python import to_native_str


def reppyAvailable():
    # check if reppy parser is installed
    try:
        from reppy.robots import Robots
    except ImportError:
        return False
    return True

def rerpAvailable():
    # check if robotexclusionrulesparser is installed 
    try:
        from robotexclusionrulesparser import RobotExclusionRulesParser
    except ImportError:
        return False
    return True
    

class BaseRobotParserTest():
    def _setUp(self, parser_cls):
        self.parser_cls = parser_cls

    def test_allowed(self):
        robotstxt_content = ("User-agent: * \n"
                    "Disallow: /disallowed \n"
                    "Allow: /allowed \n"
                    "Crawl-delay: 10".encode('utf-8'))
        rp = self.parser_cls(robotstxt_content, spider=None)
        self.assertTrue(rp.allowed("https://www.site.local/allowed", "*"))
        self.assertFalse(rp.allowed("https://www.site.local/disallowed", "*"))

    def test_allowed_wildcards(self):
        robotstxt_content =  """User-agent: first
                                Disallow: /disallowed/*/end$    

                                User-agent: second
                                Allow: /*allowed
                                Disallow: /
                                """.encode('utf-8')
        rp = self.parser_cls(robotstxt_content, spider=None)

        self.assertTrue(rp.allowed("https://www.site.local/disallowed", "first"))
        self.assertFalse(rp.allowed("https://www.site.local/disallowed/xyz/end", "first"))
        self.assertFalse(rp.allowed("https://www.site.local/disallowed/abc/end", "first"))
        self.assertTrue(rp.allowed("https://www.site.local/disallowed/xyz/endinglater", "first"))

        self.assertTrue(rp.allowed("https://www.site.local/allowed", "second"))
        self.assertTrue(rp.allowed("https://www.site.local/is_still_allowed", "second"))
        self.assertTrue(rp.allowed("https://www.site.local/is_allowed_too", "second"))

    def test_length_based_precedence(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: / \n"
                            "Allow: /page".encode('utf-8'))
        rp = self.parser_cls(robotstxt_content, spider=None)
        self.assertTrue(rp.allowed("https://www.site.local/page", "*"))

    def test_order_based_precedence(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: / \n"
                            "Allow: /page".encode('utf-8'))
        rp = self.parser_cls(robotstxt_content, spider=None)
        self.assertFalse(rp.allowed("https://www.site.local/page", "*"))      
    
    def test_sitemaps(self):
        robotstxt_content = ("User-agent: * \n"
                    "Disallow: /disallowed \n"
                    "Allow: /allowed \n"
                    "Sitemap: https://site.local/sitemap.xml".encode('utf-8'))
        rp = self.parser_cls(robotstxt_content, spider=None)
        sitemaps = list(rp.sitemaps())
        self.assertTrue(len(sitemaps) == 1)
        self.assertTrue("https://site.local/sitemap.xml" in sitemaps)

    def test_no_sitemaps(self):
        robotstxt_content = ("User-agent: * \n"
                    "Disallow: /disallowed \n"
                    "Allow: /allowed \n"
                    "Crawl-delay: 10".encode('utf-8'))
        rp = self.parser_cls(robotstxt_content, spider=None)
        self.assertTrue(not list(rp.sitemaps()))

    def test_no_preferred_host(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Crawl-delay: 10".encode('utf-8'))
        rp = self.parser_cls(robotstxt_content, spider=None)
        self.assertTrue(rp.preferred_host() is None)

    def test_crawl_delay(self):
        robotstxt_content = ("User-agent: * \n"
                            "Disallow: /disallowed \n"
                            "Allow: /allowed \n"
                            "Crawl-delay: 10".encode('utf-8'))
        rp = self.parser_cls(robotstxt_content, spider=None)
        self.assertTrue(rp.crawl_delay('*') == 10.0)

    def test_no_crawl_delay(self):
        robotstxt_content = ("User-agent: * \n"
                    "Disallow: /disallowed \n"
                    "Allow: /allowed".encode('utf-8'))
        rp = self.parser_cls(robotstxt_content, spider=None)
        self.assertTrue(rp.crawl_delay('*') is None)

    def test_empty_response(self):
        """empty response should equal 'allow all'"""
        rp = self.parser_cls(b'', spider=None)
        self.assertTrue(rp.allowed("https://site.local/", "*"))
        self.assertTrue(rp.allowed("https://site.local/", "chrome"))
        self.assertTrue(rp.allowed("https://site.local/index.html", "*"))
        self.assertTrue(rp.allowed("https://site.local/disallowed", "*"))

    def test_garbage_response(self):
        """garbage response should be discarded, equal 'allow all'"""
        robotstxt_content = b'GIF89a\xd3\x00\xfe\x00\xa2'
        rp = self.parser_cls(robotstxt_content, spider=None)
        self.assertTrue(rp.allowed("https://site.local/", "*"))
        self.assertTrue(rp.allowed("https://site.local/", "chrome"))
        self.assertTrue(rp.allowed("https://site.local/index.html", "*"))
        self.assertTrue(rp.allowed("https://site.local/disallowed", "*"))

    def test_unicode_url_and_useragent(self):
        robotstxt_content = u"""
        User-Agent: *
        Disallow: /admin/
        Disallow: /static/
        # taken from https://en.wikipedia.org/robots.txt
        Disallow: /wiki/K%C3%A4ytt%C3%A4j%C3%A4:
        Disallow: /wiki/Käyttäjä:

        User-Agent: UnicödeBöt
        Disallow: /some/randome/page.html""".encode('utf-8')
        rp = self.parser_cls(robotstxt_content, spider=None)
        self.assertTrue(rp.allowed("https://site.local/", "*"))
        self.assertFalse(rp.allowed("https://site.local/admin/", "*"))
        self.assertFalse(rp.allowed("https://site.local/static/", "*"))
        self.assertTrue(rp.allowed("https://site.local/admin/", u"UnicödeBöt"))
        self.assertFalse(rp.allowed("https://site.local/wiki/K%C3%A4ytt%C3%A4j%C3%A4:", "*"))
        self.assertFalse(rp.allowed(u"https://site.local/wiki/Käyttäjä:", "*"))
        self.assertTrue(rp.allowed("https://site.local/some/randome/page.html", "*"))
        self.assertFalse(rp.allowed("https://site.local/some/randome/page.html", u"UnicödeBöt"))

class PythonRobotParserTest(BaseRobotParserTest, unittest.TestCase):
    def setUp(self):
        from scrapy.extensions.robotstxtparser import PythonRobotParser
        super(PythonRobotParserTest, self)._setUp(PythonRobotParser)

    def test_sitemaps(self):
        """RobotFileParse doesn't support Sitemap directive. PythonRobotParser should always return an empty generator."""
        from scrapy.extensions.robotstxtparser import PythonRobotParser
        robotstxt_content = ("User-agent: * \n"
            "Disallow: /disallowed \n"
            "Allow: /allowed \n"
            "Sitemap: https://site.local/sitemap.xml".encode('utf-8'))
        rp = PythonRobotParser(robotstxt_content, spider=None)
        self.assertTrue(not list(rp.sitemaps()))

    def test_crawl_delay(self):
        """RobotFileParser does not support Crawl-delay directive for Python version < 3.6"""
        from scrapy.extensions.robotstxtparser import PythonRobotParser
        from six.moves.urllib_robotparser import RobotFileParser
        if hasattr(RobotFileParser, "crawl_delay"):
            super(PythonRobotParserTest, self).test_crawl_delay()
        else:
            robotstxt_content = ("User-agent: * \n"
                                "Disallow: /disallowed \n"
                                "Allow: /allowed \n"
                                "Crawl-delay: 10".encode('utf-8'))
            rp = PythonRobotParser(robotstxt_content, spider=None)
            self.assertTrue(rp.crawl_delay("*") is None)

    def test_length_based_precedence(self):
        raise unittest.SkipTest("RobotFileParser does not support length based directives precedence.")

    def test_allowed_wildcards(self):
        raise unittest.SkipTest("RobotFileParser does not support wildcards.")


class ReppyRobotParserTest(BaseRobotParserTest, unittest.TestCase):
    if not reppyAvailable():
        skip = "Reppy parser is not installed"
    
    def setUp(self):
        from scrapy.extensions.robotstxtparser import ReppyRobotParser
        super(ReppyRobotParserTest, self)._setUp(ReppyRobotParser)

    def test_order_based_precedence(self):
        raise unittest.SkipTest("Rerp does not support order based directives precedence.")


class RerpRobotParserTest(BaseRobotParserTest, unittest.TestCase):
    if not rerpAvailable():
        skip = "Rerp parser is not installed"
    
    def setUp(self):
        from scrapy.extensions.robotstxtparser import RerpRobotParser
        super(RerpRobotParserTest, self)._setUp(RerpRobotParser)

    def test_length_based_precedence(self):
        raise unittest.SkipTest("Rerp does not support length based directives precedence.")
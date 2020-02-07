# coding=utf-8
from twisted.trial import unittest


def reppy_available():
    # check if reppy parser is installed
    try:
        from reppy.robots import Robots  # noqa: F401
    except ImportError:
        return False
    return True


def rerp_available():
    # check if robotexclusionrulesparser is installed
    try:
        from robotexclusionrulesparser import RobotExclusionRulesParser  # noqa: F401
    except ImportError:
        return False
    return True


def protego_available():
    # check if protego parser is installed
    try:
        from protego import Protego  # noqa: F401
    except ImportError:
        return False
    return True


class BaseRobotParserTest:
    def _setUp(self, parser_cls):
        self.parser_cls = parser_cls

    def test_allowed(self):
        robotstxt_robotstxt_body = ("User-agent: * \n"
                                    "Disallow: /disallowed \n"
                                    "Allow: /allowed \n"
                                    "Crawl-delay: 10".encode('utf-8'))
        rp = self.parser_cls.from_crawler(crawler=None, robotstxt_body=robotstxt_robotstxt_body)
        self.assertTrue(rp.allowed("https://www.site.local/allowed", "*"))
        self.assertFalse(rp.allowed("https://www.site.local/disallowed", "*"))

    def test_allowed_wildcards(self):
        robotstxt_robotstxt_body = """User-agent: first
                                Disallow: /disallowed/*/end$

                                User-agent: second
                                Allow: /*allowed
                                Disallow: /
                                """.encode('utf-8')
        rp = self.parser_cls.from_crawler(crawler=None, robotstxt_body=robotstxt_robotstxt_body)

        self.assertTrue(rp.allowed("https://www.site.local/disallowed", "first"))
        self.assertFalse(rp.allowed("https://www.site.local/disallowed/xyz/end", "first"))
        self.assertFalse(rp.allowed("https://www.site.local/disallowed/abc/end", "first"))
        self.assertTrue(rp.allowed("https://www.site.local/disallowed/xyz/endinglater", "first"))

        self.assertTrue(rp.allowed("https://www.site.local/allowed", "second"))
        self.assertTrue(rp.allowed("https://www.site.local/is_still_allowed", "second"))
        self.assertTrue(rp.allowed("https://www.site.local/is_allowed_too", "second"))

    def test_length_based_precedence(self):
        robotstxt_robotstxt_body = ("User-agent: * \n"
                                    "Disallow: / \n"
                                    "Allow: /page".encode('utf-8'))
        rp = self.parser_cls.from_crawler(crawler=None, robotstxt_body=robotstxt_robotstxt_body)
        self.assertTrue(rp.allowed("https://www.site.local/page", "*"))

    def test_order_based_precedence(self):
        robotstxt_robotstxt_body = ("User-agent: * \n"
                                    "Disallow: / \n"
                                    "Allow: /page".encode('utf-8'))
        rp = self.parser_cls.from_crawler(crawler=None, robotstxt_body=robotstxt_robotstxt_body)
        self.assertFalse(rp.allowed("https://www.site.local/page", "*"))

    def test_empty_response(self):
        """empty response should equal 'allow all'"""
        rp = self.parser_cls.from_crawler(crawler=None, robotstxt_body=b'')
        self.assertTrue(rp.allowed("https://site.local/", "*"))
        self.assertTrue(rp.allowed("https://site.local/", "chrome"))
        self.assertTrue(rp.allowed("https://site.local/index.html", "*"))
        self.assertTrue(rp.allowed("https://site.local/disallowed", "*"))

    def test_garbage_response(self):
        """garbage response should be discarded, equal 'allow all'"""
        robotstxt_robotstxt_body = b'GIF89a\xd3\x00\xfe\x00\xa2'
        rp = self.parser_cls.from_crawler(crawler=None, robotstxt_body=robotstxt_robotstxt_body)
        self.assertTrue(rp.allowed("https://site.local/", "*"))
        self.assertTrue(rp.allowed("https://site.local/", "chrome"))
        self.assertTrue(rp.allowed("https://site.local/index.html", "*"))
        self.assertTrue(rp.allowed("https://site.local/disallowed", "*"))

    def test_unicode_url_and_useragent(self):
        robotstxt_robotstxt_body = u"""
        User-Agent: *
        Disallow: /admin/
        Disallow: /static/
        # taken from https://en.wikipedia.org/robots.txt
        Disallow: /wiki/K%C3%A4ytt%C3%A4j%C3%A4:
        Disallow: /wiki/Käyttäjä:

        User-Agent: UnicödeBöt
        Disallow: /some/randome/page.html""".encode('utf-8')
        rp = self.parser_cls.from_crawler(crawler=None, robotstxt_body=robotstxt_robotstxt_body)
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
        from scrapy.robotstxt import PythonRobotParser
        super(PythonRobotParserTest, self)._setUp(PythonRobotParser)

    def test_length_based_precedence(self):
        raise unittest.SkipTest("RobotFileParser does not support length based directives precedence.")

    def test_allowed_wildcards(self):
        raise unittest.SkipTest("RobotFileParser does not support wildcards.")


class ReppyRobotParserTest(BaseRobotParserTest, unittest.TestCase):
    if not reppy_available():
        skip = "Reppy parser is not installed"

    def setUp(self):
        from scrapy.robotstxt import ReppyRobotParser
        super(ReppyRobotParserTest, self)._setUp(ReppyRobotParser)

    def test_order_based_precedence(self):
        raise unittest.SkipTest("Reppy does not support order based directives precedence.")


class RerpRobotParserTest(BaseRobotParserTest, unittest.TestCase):
    if not rerp_available():
        skip = "Rerp parser is not installed"

    def setUp(self):
        from scrapy.robotstxt import RerpRobotParser
        super(RerpRobotParserTest, self)._setUp(RerpRobotParser)

    def test_length_based_precedence(self):
        raise unittest.SkipTest("Rerp does not support length based directives precedence.")


class ProtegoRobotParserTest(BaseRobotParserTest, unittest.TestCase):
    if not protego_available():
        skip = "Protego parser is not installed"

    def setUp(self):
        from scrapy.robotstxt import ProtegoRobotParser
        super(ProtegoRobotParserTest, self)._setUp(ProtegoRobotParser)

    def test_order_based_precedence(self):
        raise unittest.SkipTest("Protego does not support order based directives precedence.")

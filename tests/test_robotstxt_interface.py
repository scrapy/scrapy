from twisted.trial import unittest

from scrapy.robotstxt import decode_robotstxt


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
        robotstxt_robotstxt_body = (
            b"User-agent: * \n"
            b"Disallow: /disallowed \n"
            b"Allow: /allowed \n"
            b"Crawl-delay: 10"
        )
        rp = self.parser_cls.from_crawler(
            crawler=None, robotstxt_body=robotstxt_robotstxt_body
        )
        self.assertTrue(rp.allowed("https://www.site.local/allowed", "*"))
        self.assertFalse(rp.allowed("https://www.site.local/disallowed", "*"))

    def test_allowed_wildcards(self):
        robotstxt_robotstxt_body = b"""User-agent: first
                                Disallow: /disallowed/*/end$

                                User-agent: second
                                Allow: /*allowed
                                Disallow: /
                                """
        rp = self.parser_cls.from_crawler(
            crawler=None, robotstxt_body=robotstxt_robotstxt_body
        )

        self.assertTrue(rp.allowed("https://www.site.local/disallowed", "first"))
        self.assertFalse(
            rp.allowed("https://www.site.local/disallowed/xyz/end", "first")
        )
        self.assertFalse(
            rp.allowed("https://www.site.local/disallowed/abc/end", "first")
        )
        self.assertTrue(
            rp.allowed("https://www.site.local/disallowed/xyz/endinglater", "first")
        )

        self.assertTrue(rp.allowed("https://www.site.local/allowed", "second"))
        self.assertTrue(rp.allowed("https://www.site.local/is_still_allowed", "second"))
        self.assertTrue(rp.allowed("https://www.site.local/is_allowed_too", "second"))

    def test_length_based_precedence(self):
        robotstxt_robotstxt_body = b"User-agent: * \n" b"Disallow: / \n" b"Allow: /page"
        rp = self.parser_cls.from_crawler(
            crawler=None, robotstxt_body=robotstxt_robotstxt_body
        )
        self.assertTrue(rp.allowed("https://www.site.local/page", "*"))

    def test_order_based_precedence(self):
        robotstxt_robotstxt_body = b"User-agent: * \n" b"Disallow: / \n" b"Allow: /page"
        rp = self.parser_cls.from_crawler(
            crawler=None, robotstxt_body=robotstxt_robotstxt_body
        )
        self.assertFalse(rp.allowed("https://www.site.local/page", "*"))

    def test_empty_response(self):
        """empty response should equal 'allow all'"""
        rp = self.parser_cls.from_crawler(crawler=None, robotstxt_body=b"")
        self.assertTrue(rp.allowed("https://site.local/", "*"))
        self.assertTrue(rp.allowed("https://site.local/", "chrome"))
        self.assertTrue(rp.allowed("https://site.local/index.html", "*"))
        self.assertTrue(rp.allowed("https://site.local/disallowed", "*"))

    def test_garbage_response(self):
        """garbage response should be discarded, equal 'allow all'"""
        robotstxt_robotstxt_body = b"GIF89a\xd3\x00\xfe\x00\xa2"
        rp = self.parser_cls.from_crawler(
            crawler=None, robotstxt_body=robotstxt_robotstxt_body
        )
        self.assertTrue(rp.allowed("https://site.local/", "*"))
        self.assertTrue(rp.allowed("https://site.local/", "chrome"))
        self.assertTrue(rp.allowed("https://site.local/index.html", "*"))
        self.assertTrue(rp.allowed("https://site.local/disallowed", "*"))

    def test_unicode_url_and_useragent(self):
        robotstxt_robotstxt_body = """
        User-Agent: *
        Disallow: /admin/
        Disallow: /static/
        # taken from https://en.wikipedia.org/robots.txt
        Disallow: /wiki/K%C3%A4ytt%C3%A4j%C3%A4:
        Disallow: /wiki/Käyttäjä:

        User-Agent: UnicödeBöt
        Disallow: /some/randome/page.html""".encode()
        rp = self.parser_cls.from_crawler(
            crawler=None, robotstxt_body=robotstxt_robotstxt_body
        )
        self.assertTrue(rp.allowed("https://site.local/", "*"))
        self.assertFalse(rp.allowed("https://site.local/admin/", "*"))
        self.assertFalse(rp.allowed("https://site.local/static/", "*"))
        self.assertTrue(rp.allowed("https://site.local/admin/", "UnicödeBöt"))
        self.assertFalse(
            rp.allowed("https://site.local/wiki/K%C3%A4ytt%C3%A4j%C3%A4:", "*")
        )
        self.assertFalse(rp.allowed("https://site.local/wiki/Käyttäjä:", "*"))
        self.assertTrue(rp.allowed("https://site.local/some/randome/page.html", "*"))
        self.assertFalse(
            rp.allowed("https://site.local/some/randome/page.html", "UnicödeBöt")
        )


class DecodeRobotsTxtTest(unittest.TestCase):
    def test_native_string_conversion(self):
        robotstxt_body = b"User-agent: *\nDisallow: /\n"
        decoded_content = decode_robotstxt(
            robotstxt_body, spider=None, to_native_str_type=True
        )
        self.assertEqual(decoded_content, "User-agent: *\nDisallow: /\n")

    def test_decode_utf8(self):
        robotstxt_body = b"User-agent: *\nDisallow: /\n"
        decoded_content = decode_robotstxt(robotstxt_body, spider=None)
        self.assertEqual(decoded_content, "User-agent: *\nDisallow: /\n")

    def test_decode_non_utf8(self):
        robotstxt_body = b"User-agent: *\n\xFFDisallow: /\n"
        decoded_content = decode_robotstxt(robotstxt_body, spider=None)
        self.assertEqual(decoded_content, "User-agent: *\nDisallow: /\n")


class PythonRobotParserTest(BaseRobotParserTest, unittest.TestCase):
    def setUp(self):
        from scrapy.robotstxt import PythonRobotParser

        super()._setUp(PythonRobotParser)

    def test_length_based_precedence(self):
        raise unittest.SkipTest(
            "RobotFileParser does not support length based directives precedence."
        )

    def test_allowed_wildcards(self):
        raise unittest.SkipTest("RobotFileParser does not support wildcards.")


class RerpRobotParserTest(BaseRobotParserTest, unittest.TestCase):
    if not rerp_available():
        skip = "Rerp parser is not installed"

    def setUp(self):
        from scrapy.robotstxt import RerpRobotParser

        super()._setUp(RerpRobotParser)

    def test_length_based_precedence(self):
        raise unittest.SkipTest(
            "Rerp does not support length based directives precedence."
        )


class ProtegoRobotParserTest(BaseRobotParserTest, unittest.TestCase):
    if not protego_available():
        skip = "Protego parser is not installed"

    def setUp(self):
        from scrapy.robotstxt import ProtegoRobotParser

        super()._setUp(ProtegoRobotParser)

    def test_order_based_precedence(self):
        raise unittest.SkipTest(
            "Protego does not support order based directives precedence."
        )

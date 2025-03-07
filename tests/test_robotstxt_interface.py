import pytest

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
            b"User-agent: * \nDisallow: /disallowed \nAllow: /allowed \nCrawl-delay: 10"
        )
        rp = self.parser_cls.from_crawler(
            crawler=None, robotstxt_body=robotstxt_robotstxt_body
        )
        assert rp.allowed("https://www.site.local/allowed", "*")
        assert not rp.allowed("https://www.site.local/disallowed", "*")

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

        assert rp.allowed("https://www.site.local/disallowed", "first")
        assert not rp.allowed("https://www.site.local/disallowed/xyz/end", "first")
        assert not rp.allowed("https://www.site.local/disallowed/abc/end", "first")
        assert rp.allowed("https://www.site.local/disallowed/xyz/endinglater", "first")

        assert rp.allowed("https://www.site.local/allowed", "second")
        assert rp.allowed("https://www.site.local/is_still_allowed", "second")
        assert rp.allowed("https://www.site.local/is_allowed_too", "second")

    def test_length_based_precedence(self):
        robotstxt_robotstxt_body = b"User-agent: * \nDisallow: / \nAllow: /page"
        rp = self.parser_cls.from_crawler(
            crawler=None, robotstxt_body=robotstxt_robotstxt_body
        )
        assert rp.allowed("https://www.site.local/page", "*")

    def test_order_based_precedence(self):
        robotstxt_robotstxt_body = b"User-agent: * \nDisallow: / \nAllow: /page"
        rp = self.parser_cls.from_crawler(
            crawler=None, robotstxt_body=robotstxt_robotstxt_body
        )
        assert not rp.allowed("https://www.site.local/page", "*")

    def test_empty_response(self):
        """empty response should equal 'allow all'"""
        rp = self.parser_cls.from_crawler(crawler=None, robotstxt_body=b"")
        assert rp.allowed("https://site.local/", "*")
        assert rp.allowed("https://site.local/", "chrome")
        assert rp.allowed("https://site.local/index.html", "*")
        assert rp.allowed("https://site.local/disallowed", "*")

    def test_garbage_response(self):
        """garbage response should be discarded, equal 'allow all'"""
        robotstxt_robotstxt_body = b"GIF89a\xd3\x00\xfe\x00\xa2"
        rp = self.parser_cls.from_crawler(
            crawler=None, robotstxt_body=robotstxt_robotstxt_body
        )
        assert rp.allowed("https://site.local/", "*")
        assert rp.allowed("https://site.local/", "chrome")
        assert rp.allowed("https://site.local/index.html", "*")
        assert rp.allowed("https://site.local/disallowed", "*")

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
        assert rp.allowed("https://site.local/", "*")
        assert not rp.allowed("https://site.local/admin/", "*")
        assert not rp.allowed("https://site.local/static/", "*")
        assert rp.allowed("https://site.local/admin/", "UnicödeBöt")
        assert not rp.allowed("https://site.local/wiki/K%C3%A4ytt%C3%A4j%C3%A4:", "*")
        assert not rp.allowed("https://site.local/wiki/Käyttäjä:", "*")
        assert rp.allowed("https://site.local/some/randome/page.html", "*")
        assert not rp.allowed("https://site.local/some/randome/page.html", "UnicödeBöt")


class TestDecodeRobotsTxt:
    def test_native_string_conversion(self):
        robotstxt_body = b"User-agent: *\nDisallow: /\n"
        decoded_content = decode_robotstxt(
            robotstxt_body, spider=None, to_native_str_type=True
        )
        assert decoded_content == "User-agent: *\nDisallow: /\n"

    def test_decode_utf8(self):
        robotstxt_body = b"User-agent: *\nDisallow: /\n"
        decoded_content = decode_robotstxt(robotstxt_body, spider=None)
        assert decoded_content == "User-agent: *\nDisallow: /\n"

    def test_decode_non_utf8(self):
        robotstxt_body = b"User-agent: *\n\xffDisallow: /\n"
        decoded_content = decode_robotstxt(robotstxt_body, spider=None)
        assert decoded_content == "User-agent: *\nDisallow: /\n"


class TestPythonRobotParser(BaseRobotParserTest):
    def setup_method(self):
        from scrapy.robotstxt import PythonRobotParser

        super()._setUp(PythonRobotParser)

    def test_length_based_precedence(self):
        pytest.skip(
            "RobotFileParser does not support length based directives precedence."
        )

    def test_allowed_wildcards(self):
        pytest.skip("RobotFileParser does not support wildcards.")


@pytest.mark.skipif(not rerp_available(), reason="Rerp parser is not installed")
class TestRerpRobotParser(BaseRobotParserTest):
    def setup_method(self):
        from scrapy.robotstxt import RerpRobotParser

        super()._setUp(RerpRobotParser)

    def test_length_based_precedence(self):
        pytest.skip("Rerp does not support length based directives precedence.")


@pytest.mark.skipif(not protego_available(), reason="Protego parser is not installed")
class TestProtegoRobotParser(BaseRobotParserTest):
    def setup_method(self):
        from scrapy.robotstxt import ProtegoRobotParser

        super()._setUp(ProtegoRobotParser)

    def test_order_based_precedence(self):
        pytest.skip("Protego does not support order based directives precedence.")

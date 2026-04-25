"""
Tests for deny_tags and deny_attrs parameters in LxmlLinkExtractor.
Related to GitHub issue #6321.
"""

import pytest
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor


def make_response(html: str, url: str = "http://example.com") -> HtmlResponse:
    return HtmlResponse(url=url, body=html.encode("utf-8"))


class TestDenyTags:
    def test_deny_tags_excludes_matching_tag(self):
        """Links inside a denied tag should not be extracted."""
        html = """
        <html><body>
            <a href="http://example.com/keep">keep this</a>
            <script src="http://example.com/script-link">script</script>
        </body></html>
        """
        le = LinkExtractor(tags=["a", "script"], attrs=["href", "src"], deny_tags=["script"])
        response = make_response(html)
        links = [l.url for l in le.extract_links(response)]
        assert "http://example.com/keep" in links
        assert "http://example.com/script-link" not in links

    def test_deny_tags_single_string(self):
        """deny_tags should accept a single string, not just a list."""
        html = """
        <html><body>
            <a href="http://example.com/keep">keep</a>
            <script src="http://example.com/skip">skip</script>
        </body></html>
        """
        le = LinkExtractor(tags=["a", "script"], attrs=["href", "src"], deny_tags="script")
        response = make_response(html)
        links = [l.url for l in le.extract_links(response)]
        assert "http://example.com/keep" in links
        assert "http://example.com/skip" not in links

    def test_deny_tags_multiple(self):
        """Multiple tags can be denied at once."""
        html = """
        <html><body>
            <a href="http://example.com/keep">keep</a>
            <script src="http://example.com/skip-script">skip</script>
            <iframe src="http://example.com/skip-iframe">skip</iframe>
        </body></html>
        """
        le = LinkExtractor(
            tags=["a", "script", "iframe"],
            attrs=["href", "src"],
            deny_tags=["script", "iframe"],
        )
        response = make_response(html)
        links = [l.url for l in le.extract_links(response)]
        assert "http://example.com/keep" in links
        assert "http://example.com/skip-script" not in links
        assert "http://example.com/skip-iframe" not in links

    def test_deny_tags_empty_default(self):
        """With no deny_tags set, all matching tags should be extracted normally."""
        html = """
        <html><body>
            <a href="http://example.com/one">one</a>
            <a href="http://example.com/two">two</a>
        </body></html>
        """
        le = LinkExtractor()
        response = make_response(html)
        links = [l.url for l in le.extract_links(response)]
        assert "http://example.com/one" in links
        assert "http://example.com/two" in links

    def test_deny_tags_does_not_affect_other_tags(self):
        """Denying one tag should not affect links from other tags."""
        html = """
        <html><body>
            <a href="http://example.com/a-link">a link</a>
            <area href="http://example.com/area-link">
            <script src="http://example.com/script-link">script</script>
        </body></html>
        """
        le = LinkExtractor(
            tags=["a", "area", "script"],
            attrs=["href", "src"],
            deny_tags=["script"],
        )
        response = make_response(html)
        links = [l.url for l in le.extract_links(response)]
        assert "http://example.com/a-link" in links
        assert "http://example.com/area-link" in links
        assert "http://example.com/script-link" not in links


class TestDenyAttrs:
    def test_deny_attrs_excludes_matching_attr(self):
        """Links found via a denied attribute should not be extracted."""
        html = """
        <html><body>
            <a href="http://example.com/keep">keep</a>
            <a data-url="http://example.com/skip">skip</a>
        </body></html>
        """
        le = LinkExtractor(attrs=["href", "data-url"], deny_attrs=["data-url"])
        response = make_response(html)
        links = [l.url for l in le.extract_links(response)]
        assert "http://example.com/keep" in links
        assert "http://example.com/skip" not in links

    def test_deny_attrs_single_string(self):
        """deny_attrs should accept a single string."""
        html = """
        <html><body>
            <a href="http://example.com/keep">keep</a>
            <a data-url="http://example.com/skip">skip</a>
        </body></html>
        """
        le = LinkExtractor(attrs=["href", "data-url"], deny_attrs="data-url")
        response = make_response(html)
        links = [l.url for l in le.extract_links(response)]
        assert "http://example.com/keep" in links
        assert "http://example.com/skip" not in links

    def test_deny_attrs_multiple(self):
        """Multiple attributes can be denied at once."""
        html = """
        <html><body>
            <a href="http://example.com/keep">keep</a>
            <a data-url="http://example.com/skip1">skip1</a>
            <a data-href="http://example.com/skip2">skip2</a>
        </body></html>
        """
        le = LinkExtractor(
            attrs=["href", "data-url", "data-href"],
            deny_attrs=["data-url", "data-href"],
        )
        response = make_response(html)
        links = [l.url for l in le.extract_links(response)]
        assert "http://example.com/keep" in links
        assert "http://example.com/skip1" not in links
        assert "http://example.com/skip2" not in links

    def test_deny_attrs_empty_default(self):
        """With no deny_attrs, all matching attrs are extracted normally."""
        html = """
        <html><body>
            <a href="http://example.com/one">one</a>
            <a href="http://example.com/two">two</a>
        </body></html>
        """
        le = LinkExtractor()
        response = make_response(html)
        links = [l.url for l in le.extract_links(response)]
        assert len(links) == 2


class TestDenyTagsAndDenyAttrsTogether:
    def test_deny_tags_and_deny_attrs_combined(self):
        """Both deny_tags and deny_attrs should work together independently."""
        html = """
        <html><body>
            <a href="http://example.com/keep">keep</a>
            <script src="http://example.com/skip-tag">skip by tag</script>
            <a data-url="http://example.com/skip-attr">skip by attr</a>
        </body></html>
        """
        le = LinkExtractor(
            tags=["a", "script"],
            attrs=["href", "src", "data-url"],
            deny_tags=["script"],
            deny_attrs=["data-url"],
        )
        response = make_response(html)
        links = [l.url for l in le.extract_links(response)]
        assert "http://example.com/keep" in links
        assert "http://example.com/skip-tag" not in links
        assert "http://example.com/skip-attr" not in links

    def test_backward_compatibility(self):
        """Existing behavior with no deny_tags or deny_attrs must be unchanged."""
        html = """
        <html><body>
            <a href="http://example.com/page1">page1</a>
            <a href="http://example.com/page2">page2</a>
            <area href="http://example.com/area">area</area>
        </body></html>
        """
        le = LinkExtractor()
        response = make_response(html)
        links = [l.url for l in le.extract_links(response)]
        assert "http://example.com/page1" in links
        assert "http://example.com/page2" in links
        assert "http://example.com/area" in links

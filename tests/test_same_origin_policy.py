import pytest
from scrapy import Spider
from scrapy.utils.url import url_is_from_any_domain, url_is_from_spider


class TestSameOriginPolicy:
    def test_url_is_from_any_domain_standard(self):
        # Test standard behavior (non-strict)
        assert url_is_from_any_domain("http://example.com", ["example.com"])
        assert url_is_from_any_domain("https://example.com", ["example.com"])
        assert url_is_from_any_domain("http://sub.example.com", ["example.com"])
        assert not url_is_from_any_domain("http://example.net", ["example.com"])

    def test_url_is_from_any_domain_strict(self):
        # Test strict same-origin policy
        assert url_is_from_any_domain("http://example.com", ["example.com"], strict=True)
        assert url_is_from_any_domain("https://example.com", ["example.com"], strict=True)
        assert url_is_from_any_domain("http://sub.example.com", ["example.com"], strict=True)

        # Test with scheme-specific domains
        assert url_is_from_any_domain("http://example.com", ["http://example.com"], strict=True)
        assert not url_is_from_any_domain("https://example.com", ["http://example.com"], strict=True)

        # Test with port-specific domains
        assert url_is_from_any_domain("http://example.com:8080", ["example.com:8080"], strict=True)
        assert not url_is_from_any_domain("http://example.com", ["example.com:8080"], strict=True)

    def test_url_is_from_any_domain_wildcards(self):
        # Test wildcard domains
        assert url_is_from_any_domain("http://sub.example.com", ["*.example.com"])
        assert url_is_from_any_domain("http://sub.sub.example.com", ["*.example.com"])
        assert url_is_from_any_domain("http://example.com", ["*.example.com"])

        # Test wildcards with strict mode
        assert url_is_from_any_domain("http://sub.example.com", ["*.example.com"], strict=True)
        assert url_is_from_any_domain("http://sub.sub.example.com", ["*.example.com"], strict=True)
        assert not url_is_from_any_domain("http://example.com", ["*.example.com"], strict=True)


class TestSpiderSameOriginPolicy:
    def test_spider_default_behavior(self):
        # Test default behavior (non-strict)
        spider = Spider(name="example", allowed_domains=["example.com"])
        assert url_is_from_spider("http://example.com", spider)
        assert url_is_from_spider("https://example.com", spider)
        assert url_is_from_spider("http://sub.example.com", spider)
        assert not url_is_from_spider("http://example.net", spider)

    def test_spider_strict_origins(self):
        # Test with strict_origins enabled
        spider = Spider(name="example", allowed_domains=["http://example.com"], strict_origins=True)
        assert url_is_from_spider("http://example.com", spider)
        assert not url_is_from_spider("https://example.com", spider)
        assert not url_is_from_spider("http://sub.example.com", spider)

    def test_spider_strict_origins_wildcards(self):
        # Test with strict_origins and wildcards
        spider = Spider(name="example", allowed_domains=["*.example.com"], strict_origins=True)
        assert url_is_from_spider("http://sub.example.com", spider)
        assert not url_is_from_spider("http://example.com", spider)

    def test_spider_strict_origins_multiple_domains(self):
        # Test with multiple domains
        spider = Spider(
            name="example", 
            allowed_domains=["http://example.com", "https://example.org", "*.example.net"],
            strict_origins=True
        )
        assert url_is_from_spider("http://example.com", spider)
        assert url_is_from_spider("https://example.org", spider)
        assert url_is_from_spider("http://sub.example.net", spider)
        assert not url_is_from_spider("https://example.com", spider)
        assert not url_is_from_spider("http://example.org", spider)
        assert not url_is_from_spider("http://example.net", spider)

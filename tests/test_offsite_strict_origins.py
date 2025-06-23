import re
from unittest import TestCase

import pytest
from scrapy import Request, Spider
from scrapy.downloadermiddlewares.offsite import OffsiteMiddleware
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Response
from scrapy.utils.test import get_crawler
from scrapy.utils.url import url_is_from_any_domain, url_is_from_spider


class StrictOriginsSpider(Spider):
    """Test spider with strict_origins enabled"""
    name = 'strict'
    strict_origins = True

    def __init__(self, allowed_domains=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed_domains = allowed_domains or []


class StandardSpider(Spider):
    """Test spider with standard (non-strict) domain handling"""
    name = 'standard'

    def __init__(self, allowed_domains=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed_domains = allowed_domains or []


class TestStrictOrigins(TestCase):

    def setUp(self):
        self.spider = StrictOriginsSpider()
        crawler = get_crawler(StrictOriginsSpider)
        self.mw = OffsiteMiddleware.from_crawler(crawler)
        self.mw.spider_opened(self.spider)

    def test_schemes_are_distinguished(self):
        """Test that http and https are considered different origins"""
        self.spider.allowed_domains = ['http://example.com']

        # Same scheme should be allowed
        req1 = Request('http://example.com/page')
        assert self.mw.should_follow(req1, self.spider) is True

        # Different scheme should be blocked
        req2 = Request('https://example.com/page')
        assert self.mw.should_follow(req2, self.spider) is False

    def test_subdomains_handling(self):
        """Test that subdomains are handled correctly in strict mode"""
        # Standard domain still allows subdomains
        self.spider.allowed_domains = ['example.com']
        req1 = Request('http://sub.example.com/page')
        req2 = Request('http://example.com/page')
        assert self.mw.should_follow(req1, self.spider) is True
        assert self.mw.should_follow(req2, self.spider) is True

        # Wildcard domain only matches subdomains in strict mode
        self.spider.allowed_domains = ['*.example.com']
        req3 = Request('http://sub.example.com/page')
        req4 = Request('http://example.com/page')
        assert self.mw.should_follow(req3, self.spider) is True
        assert self.mw.should_follow(req4, self.spider) is False

    def test_full_url_in_allowed_domains(self):
        """Test that full URLs in allowed_domains work correctly"""
        self.spider.allowed_domains = ['https://example.com:8080']

        # Exact match should be allowed
        req1 = Request('https://example.com:8080/page')
        assert self.mw.should_follow(req1, self.spider) is True

        # Different scheme should be blocked
        req2 = Request('http://example.com:8080/page')
        assert self.mw.should_follow(req2, self.spider) is False

        # Different port should be blocked
        req3 = Request('https://example.com/page')
        assert self.mw.should_follow(req3, self.spider) is False

    def test_multiple_domains(self):
        """Test multiple domain specifications together"""
        self.spider.allowed_domains = [
            'http://example.com',  # Specific protocol
            '*.example.org',      # Wildcard subdomains
            'example.net'         # Standard domain
        ]

        # These should be allowed
        assert self.mw.should_follow(Request('http://example.com/page'), self.spider) is True
        assert self.mw.should_follow(Request('http://sub.example.org/page'), self.spider) is True
        assert self.mw.should_follow(Request('http://example.net/page'), self.spider) is True
        assert self.mw.should_follow(Request('http://sub.example.net/page'), self.spider) is True

        # These should be blocked
        assert self.mw.should_follow(Request('https://example.com/page'), self.spider) is False
        assert self.mw.should_follow(Request('http://example.org/page'), self.spider) is False

    def test_process_request_raises_ignorerequest(self):
        """Test that process_request raises IgnoreRequest for offsite URLs"""
        self.spider.allowed_domains = ['http://example.com']

        # Allowed URL should not raise
        req1 = Request('http://example.com/page')
        self.mw.process_request(req1, self.spider)  # Should not raise

        # Blocked URL should raise IgnoreRequest
        req2 = Request('https://example.com/page')
        with pytest.raises(IgnoreRequest):
            self.mw.process_request(req2, self.spider)


class TestURLIsFunctions(TestCase):
    """Test the url_is_from_any_domain and url_is_from_spider functions"""

    def test_url_is_from_any_domain_strict(self):
        """Test url_is_from_any_domain with strict=True"""
        # Standard domain matching
        assert url_is_from_any_domain('http://example.com', ['example.com'], strict=False) is True
        assert url_is_from_any_domain('http://example.com', ['example.com'], strict=True) is True

        # Subdomain matching
        assert url_is_from_any_domain('http://sub.example.com', ['example.com'], strict=False) is True
        assert url_is_from_any_domain('http://sub.example.com', ['example.com'], strict=True) is True

        # Scheme-specific matching
        assert url_is_from_any_domain('http://example.com', ['http://example.com'], strict=False) is True
        assert url_is_from_any_domain('http://example.com', ['http://example.com'], strict=True) is True
        assert url_is_from_any_domain('https://example.com', ['http://example.com'], strict=False) is True
        assert url_is_from_any_domain('https://example.com', ['http://example.com'], strict=True) is False

        # Wildcard domain matching
        assert url_is_from_any_domain('http://sub.example.com', ['*.example.com'], strict=False) is True
        assert url_is_from_any_domain('http://sub.example.com', ['*.example.com'], strict=True) is True
        assert url_is_from_any_domain('http://example.com', ['*.example.com'], strict=False) is True
        assert url_is_from_any_domain('http://example.com', ['*.example.com'], strict=True) is False

    def test_url_is_from_spider(self):
        """Test url_is_from_spider with and without strict_origins"""
        # Standard spider (non-strict)
        spider1 = StandardSpider(allowed_domains=['example.com'])
        assert url_is_from_spider('http://example.com', spider1) is True
        assert url_is_from_spider('https://example.com', spider1) is True
        assert url_is_from_spider('http://sub.example.com', spider1) is True

        # Strict spider with standard domain
        spider2 = StrictOriginsSpider(allowed_domains=['example.com'])
        assert url_is_from_spider('http://example.com', spider2) is True
        assert url_is_from_spider('https://example.com', spider2) is True
        assert url_is_from_spider('http://sub.example.com', spider2) is True

        # Strict spider with URL in allowed_domains
        spider3 = StrictOriginsSpider(allowed_domains=['http://example.com'])
        assert url_is_from_spider('http://example.com', spider3) is True
        assert url_is_from_spider('https://example.com', spider3) is False

        # Strict spider with wildcard domain
        spider4 = StrictOriginsSpider(allowed_domains=['*.example.com'])
        assert url_is_from_spider('http://sub.example.com', spider4) is True
        assert url_is_from_spider('http://example.com', spider4) is False

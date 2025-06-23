import pytest
from types import SimpleNamespace
from scrapy.spidermiddlewares.offsite import is_url_allowed, parse_allowed_domains

class DummySpider(SimpleNamespace):
    pass

@pytest.fixture
def spider():
    return DummySpider()

def test_allowed_domains_exact_domain(spider):
    spider.allowed_domains = ["example.com"]
    allowed = parse_allowed_domains(spider.allowed_domains)
    assert is_url_allowed("http://example.com", allowed)
    assert is_url_allowed("https://example.com", allowed)
    assert not is_url_allowed("http://sub.example.com", allowed)
    assert not is_url_allowed("http://other.com", allowed)

def test_allowed_domains_full_origin(spider):
    spider.allowed_domains = ["https://example.com"]
    allowed = parse_allowed_domains(spider.allowed_domains)
    assert is_url_allowed("https://example.com", allowed)
    assert not is_url_allowed("http://example.com", allowed)
    assert not is_url_allowed("https://sub.example.com", allowed)
    assert not is_url_allowed("https://example.com:8080", allowed)

def test_allowed_domains_with_port(spider):
    spider.allowed_domains = ["http://example.com:8080"]
    allowed = parse_allowed_domains(spider.allowed_domains)
    assert is_url_allowed("http://example.com:8080", allowed)
    assert not is_url_allowed("http://example.com", allowed)
    assert not is_url_allowed("http://example.com:80", allowed)
    assert not is_url_allowed("http://sub.example.com:8080", allowed)

def test_allowed_domains_multiple(spider):
    spider.allowed_domains = ["https://example.com", "other.com"]
    allowed = parse_allowed_domains(spider.allowed_domains)
    assert is_url_allowed("https://example.com", allowed)
    assert is_url_allowed("http://other.com", allowed)
    assert not is_url_allowed("http://example.com", allowed)
    assert not is_url_allowed("https://sub.other.com", allowed)

def test_allowed_domains_empty(spider):
    spider.allowed_domains = []
    allowed = parse_allowed_domains(spider.allowed_domains)
    assert not is_url_allowed("http://example.com", allowed)

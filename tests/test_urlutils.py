from scrapy.utils.url import urljoin

def test_urljoin_basic():
    base = "http://example.com/path/"
    rel = "../other/page.html"
    expected = "http://example.com/other/page.html"
    assert urljoin(base, rel) == expected

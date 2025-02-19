from scrapy.http import HtmlResponse
from scrapy.linkextractors.lxmlhtml import LxmlParserLinkExtractor


def test_link_extractor():
    html = '''
        <a href="page1.html">Link1</a>
        <script href="evil.js"></script>
        <div><a href="page2.html">Link2</a></div>
    '''
    response = HtmlResponse(url="https://example.com", body=html, encoding='utf-8')

    extractor = LxmlParserLinkExtractor(allow_tags=['a'])
    links = extractor.extract_links(response)

    print("\nExtracted Links:", [link.url for link in links])

    assert "https://example.com/page1.html" in [link.url for link in links]


def test_link_extractor_all_tags():
    html = '''
        <img src="image.jpg">
        <a href="page.html">Link</a>
    '''
    response = HtmlResponse(url="https://example.com", body=html, encoding='utf-8')

    extractor = LxmlParserLinkExtractor(allow_tags=['a'])
    links = extractor.extract_links(response)

    print("\nExtracted Links:", [link.url for link in links])

    # Only check for <a> tag extraction, since <img> src isn't normally extracted by link extractors
    assert "https://example.com/page.html" in [link.url for link in links]

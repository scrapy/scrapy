"""
Tests for the dont_encode_url parameter in Request class.
Related to issue #7028 and #833.
"""

import pytest

from scrapy.http import Request


class TestRequestDontEncodeUrl:
    """Tests for Request.dont_encode_url parameter"""

    def test_url_encoding_default_behavior(self):
        """Test that URL encoding is enabled by default"""
        # This URL should pass through safe_url_string
        url = "http://example.com/page"
        req = Request(url)
        # By default, safe_url_string is called
        assert req.url == url
        assert req.dont_encode_url is False

    def test_url_with_slashes_in_query_params_default(self):
        """Test that slashes in query params are preserved by default with safe_url_string"""
        url = "http://example.com/api?path=/users/123&param=value"
        req = Request(url)
        # safe_url_string preserves forward slashes in query parameters
        assert req.url == url
        assert "/users/123" in req.url

    def test_url_with_slashes_dont_encode(self):
        """Test that slashes are preserved when dont_encode_url=True"""
        url = "http://example.com/api?path=/users/123&param=value"
        req = Request(url, dont_encode_url=True)
        assert req.url == url
        assert req.dont_encode_url is True
        assert "/users/123" in req.url

    def test_url_with_special_chars_dont_encode(self):
        """Test that special characters are preserved when dont_encode_url=True"""
        url = "http://example.com/search?q=hello,world&filter=a/b/c"
        req = Request(url, dont_encode_url=True)
        assert req.url == url
        assert ",world" in req.url
        assert "/b/c" in req.url

    def test_url_parameter_ordering_preserved(self):
        """Test that URL parameter ordering is preserved"""
        url = "http://example.com/page?a=1&b=2&last=important"
        req = Request(url, dont_encode_url=True)
        assert req.url == url
        # Verify the order is maintained
        assert req.url.index("a=1") < req.url.index("b=2")
        assert req.url.index("b=2") < req.url.index("last=important")

    def test_dont_encode_url_in_attributes(self):
        """Test that dont_encode_url is in the attributes tuple"""
        assert "dont_encode_url" in Request.attributes

    def test_dont_encode_url_preserved_in_replace(self):
        """Test that dont_encode_url is preserved when using replace()"""
        url1 = "http://example.com/path?key=value/with/slashes"
        req1 = Request(url1, dont_encode_url=True)

        url2 = "http://example.com/other?param=test"
        req2 = req1.replace(url=url2)

        # The dont_encode_url parameter should be preserved
        assert req2.dont_encode_url is True
        assert req2.url == url2

    def test_dont_encode_url_preserved_in_copy(self):
        """Test that dont_encode_url is preserved when using copy()"""
        url = "http://example.com/path?key=value/with/slashes"
        req1 = Request(url, dont_encode_url=True)
        req2 = req1.copy()

        assert req2.dont_encode_url is True
        assert req2.url == url

    def test_dont_encode_url_false_by_default(self):
        """Test that dont_encode_url defaults to False"""
        req = Request("http://example.com")
        assert req.dont_encode_url is False

    def test_dont_encode_url_with_already_encoded_url(self):
        """Test behavior with already percent-encoded URLs"""
        url = "http://example.com/api?path=%2Fusers%2F123"
        req = Request(url, dont_encode_url=True)
        # When dont_encode_url is True, the URL should remain exactly as given
        assert req.url == url
        assert "%2F" in req.url

    def test_dont_encode_url_to_dict(self):
        """Test that dont_encode_url is included in to_dict()"""
        url = "http://example.com/test"
        req = Request(url, dont_encode_url=True)
        req_dict = req.to_dict()

        assert "dont_encode_url" in req_dict
        assert req_dict["dont_encode_url"] is True

    def test_mixed_requests_with_and_without_encoding(self):
        """Test that different requests can have different encoding settings"""
        url1 = "http://example.com/api?path=/users/123"
        url2 = "http://example.com/api?path=/users/456"

        req1 = Request(url1, dont_encode_url=False)
        req2 = Request(url2, dont_encode_url=True)

        assert req1.dont_encode_url is False
        assert req2.dont_encode_url is True
        # Both should preserve slashes since safe_url_string does
        assert "/users/123" in req1.url
        assert "/users/456" in req2.url

    def test_dont_encode_url_with_unicode_characters(self):
        """Test that unicode characters in URLs work with dont_encode_url"""
        url = "http://example.com/search?q=hello%20world"
        req = Request(url, dont_encode_url=True)
        assert req.url == url

    def test_url_scheme_validation_with_dont_encode(self):
        """Test that URL scheme validation still works with dont_encode_url=True"""
        # Valid URLs should work
        req = Request("http://example.com", dont_encode_url=True)
        assert req.url == "http://example.com"

        # Invalid URLs (missing scheme) should still raise ValueError
        with pytest.raises(ValueError, match="Missing scheme"):
            Request("example.com", dont_encode_url=True)

    def test_dont_encode_url_with_fragment(self):
        """Test that URL fragments are preserved with dont_encode_url"""
        url = "http://example.com/page?param=value#section"
        req = Request(url, dont_encode_url=True)
        assert req.url == url
        assert "#section" in req.url

    def test_dont_encode_url_repr(self):
        """Test that Request repr works correctly with dont_encode_url"""
        url = "http://example.com/test?key=value/with/slashes"
        req = Request(url, dont_encode_url=True)
        repr_str = repr(req)
        assert "GET" in repr_str
        assert url in repr_str

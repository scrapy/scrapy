"""
Request/Response Matchers

Perform evaluation to Request or Response attributes
"""

import re

class BaseMatcher(object):
    """Base matcher. Returns True by default."""

    def matches_request(self, request):
        """Performs Request Matching"""
        return True

    def matches_response(self, response):
        """Performs Response Matching"""
        return True


class UrlMatcher(BaseMatcher):
    """Matches URL attribute"""

    def __init__(self, url):
        """Initialize url attribute"""
        self._url = url

    def matches_url(self, url):
        """Returns True if given url is equal to matcher's url"""
        return self._url == url

    def matches_request(self, request):
        """Returns True if Request's url matches initial url"""
        return self.matches_url(request.url) 

    def matches_response(self, response):
        """Returns True if Response's url matches initial url"""
        return self.matches_url(response.url)


class UrlRegexMatcher(UrlMatcher):
    """Matches URL using regular expression"""

    def __init__(self, regex, flags=0):
        """Initialize regular expression"""
        self._regex = re.compile(regex, flags)

    def matches_url(self, url):
        """Returns True if url matches regular expression"""
        return self._regex.search(url) is not None


class UrlListMatcher(UrlMatcher):
    """Matches if URL is in List"""

    def __init__(self, urls):
        self._urls = urls

    def matches_url(self, url):
        """Returns True if url is in urls list"""
        return url in self._urls

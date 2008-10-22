"""
This module provides some useful functions for working with
scrapy.http.Response objects
"""

from scrapy.xpath import XPathSelector

def new_response_from_xpaths(response, xpaths):
    """Return a new response constructed by applying the given xpaths to the
    original response body
    """
    xs = XPathSelector(response)
    parts = [''.join([n for n in xs.x(x).extract()]) for x in xpaths]
    new_body = ''.join(parts)
    return response.replace(body=new_body)

"""
This module provides some useful functions for working with
scrapy.http.Response objects
"""

from scrapy.xpath import XPathSelector
from scrapy.http.response import ResponseBody

def new_response_from_xpaths(response, xpaths):
    """Return a new response constructed by applying the given xpaths to the
    original response body
    """
    xs = XPathSelector(response)
    parts = [''.join([n for n in xs.x(x).extract()]) for x in xpaths]
    new_body_content = ''.join(parts)
    return response.replace(body=ResponseBody(content=new_body_content, declared_encoding=response.body.get_declared_encoding()))

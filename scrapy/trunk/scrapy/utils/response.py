"""
This module provides some useful functions for working with
scrapy.http.Response objects
"""

import re
from scrapy.http.response import Response

def body_or_str(obj, unicode=True):
    assert isinstance(obj, (Response, basestring)), "obj must be Response or basestring, not %s" % type(obj).__name__
    if isinstance(obj, Response):
        return obj.body_as_unicode() if unicode else obj.body
    elif isinstance(obj, str):
        return obj.decode('utf-8') if unicode else obj
    else:
        return obj if unicode else obj.encode('utf-8')

BASEURL_RE = re.compile(r'<base\s+href\s*=\s*[\"\']\s*([^\"\'\s]+)\s*[\"\']', re.I)
def get_base_url(response):
    """ Return the base url of the given response used to resolve relative links. """
    # re is used instead of xpath for eficiency reasons. In a quick
    # benchmark using timeit we got (for 50 repetitions) 0.0017 seconds
    # using re and 0.7452 using xpath
    if 'base_url' not in response.cache:
        match = BASEURL_RE.search(response.body[0:4096])
        response.cache['base_url'] = match.group(1) if match else response.url
    return response.cache['base_url']

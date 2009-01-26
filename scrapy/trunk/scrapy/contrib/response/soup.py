"""
ResponseSoup extension 

See documentation in docs/ref/extensions.rst
""" 

from BeautifulSoup import BeautifulSoup

from scrapy.http import Response


class ResponseSoup(object):
    def __init__(self):
        setattr(Response, 'getsoup', getsoup)
        setattr(Response, 'soup', property(getsoup))

def getsoup(response, **kwargs):
    # TODO: use different cache buckets depending on constructor parameters
    if 'soup' not in response.cache:
        body = response.body if response.body is not None else ""
        response.cache['soup'] = BeautifulSoup(body, **kwargs)
    return response.cache['soup']

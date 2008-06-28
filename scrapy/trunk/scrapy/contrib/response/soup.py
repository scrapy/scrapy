"""
The ResponseSoup extension causes the Response objects to grow a new method
("getsoup") which returns a (cached) BeautifulSoup object of its body, and a
"soup" attribute with the same effect. The soup argument is provided for
convenience, but you cannot pass any BeautifulSoup constructor arguments (which
you can do with the getsoup() method).

For more information about BeautifulSoup see:
http://www.crummy.com/software/BeautifulSoup/documentation.html
""" 

from BeautifulSoup import BeautifulSoup

from scrapy.http import Response


class ResponseSoup(object):
    def __init__(self):
        setattr(Response, 'getsoup', getsoup)
        setattr(Response, 'soup', property(getsoup))

def getsoup(response, **kwargs):
    if not hasattr(response, '_soup'):
        body = response.body.to_string() if response.body is not None else ""
        setattr(response, '_soup', BeautifulSoup(body, **kwargs))
    return response._soup

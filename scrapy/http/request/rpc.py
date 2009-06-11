"""
This module implements the XmlRpcRequest class which is a more convenient class
(that Request) to generate xml-rpc requests.

See documentation in docs/ref/request-response.rst
"""

import xmlrpclib

from scrapy.http.request import Request


class XmlRpcRequest(Request):

    def __init__(self, *args, **kwargs):
        if 'body' not in kwargs:
            params = kwargs.pop('params')
            methodname = kwargs.pop('methodname')
            kwargs['body'] = xmlrpclib.dumps(params, methodname)

        # spec defines that requests must use POST method
        kwargs.setdefault('method', 'POST')

        # xmlrpc query multiples times over the same url
        kwargs.setdefault('dont_filter', True)

        Request.__init__(self, *args, **kwargs)
        self.headers.setdefault('Content-Type', 'text/xml')

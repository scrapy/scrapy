"""
This module implements the XmlRpcRequest class which is a more covenient class
(that Request) to generate xml-rpc requests.

See documentation in docs/ref/request-response.rst
"""

import xmlrpclib

from scrapy.http.request import Request


class XmlRpcRequest(Request):

    def __init__(self, *args, **kwargs):
        params = kwargs.pop('params')
        methodname = kwargs.pop('methodname')
        Request.__init__(self, *args, **kwargs)
        self.body = xmlrpclib.dumps(params, methodname)
        self.headers.setdefault('Content-Type', 'text/xml')

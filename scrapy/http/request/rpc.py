"""
This module implements the XmlRpcRequest class which is a more convenient class
(that Request) to generate xml-rpc requests.

See documentation in docs/topics/request-response.rst
"""
import six
from six.moves import xmlrpc_client

from scrapy.http.request import Request
from scrapy.utils.python import get_func_args

DUMPS_ARGS = get_func_args(xmlrpc_client.dumps)



class XmlRpcRequest(Request):

    def __init__(self, *args, **kwargs):
        encoding = kwargs.get('encoding', None)
        if 'body' not in kwargs and 'params' in kwargs:
            kw = dict((k, kwargs.pop(k)) for k in DUMPS_ARGS if k in kwargs)
            kwargs['body'] = xmlrpc_client.dumps(**kw)

        # spec defines that requests must use POST method
        kwargs.setdefault('method', 'POST')

        # xmlrpc query multiples times over the same url
        kwargs.setdefault('dont_filter', True)

        # restore encoding
        if encoding is not None:
            kwargs['encoding'] = encoding

        super(XmlRpcRequest, self).__init__(*args, **kwargs)
        self.headers.setdefault('Content-Type', 'text/xml')

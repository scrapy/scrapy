"""
This module implements the XmlRpcRequest class which is a more convenient class
(that Request) to generate xml-rpc requests.

See documentation in docs/topics/request-response.rst
"""

from __future__ import annotations

import xmlrpc.client as xmlrpclib
from typing import Any

import defusedxml.xmlrpc

from scrapy.http.request import Request
from scrapy.utils.python import get_func_args

defusedxml.xmlrpc.monkey_patch()

DUMPS_ARGS = get_func_args(xmlrpclib.dumps)


class XmlRpcRequest(Request):
    def __init__(self, *args: Any, encoding: str | None = None, **kwargs: Any):
        if "body" not in kwargs and "params" in kwargs:
            kw = {k: kwargs.pop(k) for k in DUMPS_ARGS if k in kwargs}
            kwargs["body"] = xmlrpclib.dumps(**kw)

        # spec defines that requests must use POST method
        kwargs.setdefault("method", "POST")

        # xmlrpc query multiples times over the same url
        kwargs.setdefault("dont_filter", True)

        # restore encoding
        if encoding is not None:
            kwargs["encoding"] = encoding

        super().__init__(*args, **kwargs)
        self.headers.setdefault("Content-Type", "text/xml")

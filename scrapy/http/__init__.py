"""
Module containing all HTTP related classes

Use this module (instead of the more specific ones) when importing Headers,
Request and Response outside this module.
"""

from scrapy.http.headers import Headers

from scrapy.http.request import Request
from scrapy.conf import settings
if settings['FORMREQUEST_BACKEND'] == 'lxml':
    from scrapy.http.request.lxmlform import LxmlFormRequest as FormRequest
else:
    from scrapy.http.request.form import FormRequest
from scrapy.http.request.rpc import XmlRpcRequest

from scrapy.http.response import Response
from scrapy.http.response.html import HtmlResponse
from scrapy.http.response.xml import XmlResponse
from scrapy.http.response.text import TextResponse

"""
Module containing all HTTP related classes

Use this module (instead of the more specific ones) when importing Headers,
Request, Response and Url outside this module.
"""

from scrapy.http.url import Url
from scrapy.http.headers import Headers
from scrapy.http.request import Request
from scrapy.http.response import Response

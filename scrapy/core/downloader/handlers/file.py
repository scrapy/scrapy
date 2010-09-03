"""Download handler for file:// scheme"""
from __future__ import with_statement

from urllib import url2pathname

from twisted.internet import defer
from scrapy.core.downloader.responsetypes import responsetypes


class FileRequestHandler(object):
    """file download"""

    def download_request(self, request, spider):
        return defer.maybeDeferred(self._one_pass_read, request)

    def _one_pass_read(self, request):
        filepath = url2pathname(request.url.split("file://")[1])
        with open(filepath) as f:
            body = f.read()
        respcls = responsetypes.from_args(filename=filepath, body=body)
        return respcls(url=request.url, body=body)

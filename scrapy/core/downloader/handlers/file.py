"""Download handler for file:// scheme"""
from __future__ import with_statement

from urllib import url2pathname

from twisted.internet import defer
from scrapy.core.downloader.responsetypes import responsetypes


def download_file(request, spider):
    """Return a deferred for a file download."""
    return defer.maybeDeferred(_all_in_one_read_download_file, request, spider)

def _all_in_one_read_download_file(request, spider):
    filepath = url2pathname(request.url.split("file://")[1])
    with open(filepath) as f:
        body = f.read()
    respcls = responsetypes.from_args(filename=filepath, body=body)
    return respcls(url=request.url, body=body)


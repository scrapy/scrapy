from w3lib.url import file_uri_to_path
from scrapy.responsetypes import responsetypes
from scrapy.utils.decorators import defers


class FileDownloadHandler(object):
    lazy = False

    def __init__(self, settings):
        pass

    @defers
    def download_request(self, request, spider):
        filepath = file_uri_to_path(request.url)
        with open(filepath, 'rb') as fo:
            body = fo.read()
        respcls = responsetypes.from_args(filename=filepath, body=body)
        return respcls(url=request.url, body=body)

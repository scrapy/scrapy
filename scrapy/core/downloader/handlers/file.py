from w3lib.url import file_uri_to_path

from scrapy.utils.decorators import defers
from scrapy.utils.response import get_response_class


class FileDownloadHandler:
    lazy = False

    @defers
    def download_request(self, request, spider):
        filepath = file_uri_to_path(request.url)
        with open(filepath, 'rb') as fo:
            body = fo.read()
        respcls = get_response_class(url=request.url, body=body)
        return respcls(url=request.url, body=body)

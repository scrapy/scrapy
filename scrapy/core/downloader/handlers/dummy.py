"""Download handlers for OAI-PMH
"""

from sickle import Sickle

from scrapy.http import Response

class DummyDownloadHandler(object):
    def __init__(self, *args, **kwargs):
        pass

    def download_request(self, request, spider):
        url = request.url
        return Response(url, request=request)

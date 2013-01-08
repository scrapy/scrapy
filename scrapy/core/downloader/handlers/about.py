from scrapy.responsetypes import responsetypes
from scrapy.utils.decorator import defers

class AboutDownloadHandler(object):
    """Special handler for about: uris.

    See http://en.wikipedia.org/wiki/About_URI_scheme#Standardisation
    """

    @defers
    def download_request(self, request, spider):
        """Returns blank page always"""
        respcls = responsetypes.from_mimetype('text/html')
        return respcls(url=request.url, body='', encoding='utf-8')

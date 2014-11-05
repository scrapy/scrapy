"""
This module implements the FTPListResponse class which stores files
listed in FTP folders, in a dict structure. Other attributes are typical
of Response.

See documentation in docs/topics/request-response.rst
"""

from scrapy.http.response import Response

class FTPListResponse(Response):
    def __init__(self, *args, **kwargs):
        self._files = kwargs.pop('files', None)
        super(FTPListResponse, self).__init__(*args, **kwargs)
        print self.status

    @property
    def files(self):
        return self._files

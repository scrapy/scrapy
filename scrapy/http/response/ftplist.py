"""
This module implements the FTPListResponse class which adds information about
stored files in a particular FTP folder to the Response.

See documentation in docs/topics/request-response.rst
"""

from scrapy.http.response import Response

class FTPListResponse(Response):
    def __init__(self, *args, **kwargs):
        self._files = kwargs.pop('files', None)
        super(FTPListResponse, self).__init__(*args, **kwargs)

    @property
    def files(self):
        return self._files

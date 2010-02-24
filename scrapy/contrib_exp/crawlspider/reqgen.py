"""Request Generator"""
from itertools import imap

class RequestGenerator(object):
    """Extracto and process requests from response"""

    def __init__(self, req_extractors, req_processors, callback, spider=None):
        """Initialize attributes"""
        self._request_extractors = req_extractors
        self._request_processors = req_processors
        #TODO: resolve callback?
        self._callback = callback

    def generate_requests(self, response):
        """Extract and process new requests from response.
           Attach callback to each request as default callback."""
        requests = []
        for ext in self._request_extractors:
            requests.extend(ext.extract_requests(response))

        for proc in self._request_processors:
            requests = proc(requests)

        # return iterator
        # @@@ creates new Request object with callback
        return imap(lambda r: r.replace(callback=self._callback), requests)


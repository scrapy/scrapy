class BaseDownloaderMiddleware(object):
    """Base class for downloader middleware.
    """
    def process_request(self, request, spider):
        pass

    def process_response(self, request, response, spider):
        return response

    def process_exception(self, request, exception, spider):
        pass

    @classmethod
    def from_crawler(cls, crawler):
        pass

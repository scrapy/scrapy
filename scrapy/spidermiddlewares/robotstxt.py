_start_requests_processed = object()


class RobotsTxtSpiderMiddleware:
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self._send_signal = crawler.signals.send_catch_log

    def process_start_requests(self, start_requests, spider):
        # Mark start requests and reports to the downloader middleware the
        # number of them once all have been processed.
        count = 0
        for request in start_requests:
            request.meta["is_start_request"] = True
            yield request
            count += 1
        self._send_signal(_start_requests_processed, count=count)

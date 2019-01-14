from scrapy.utils.python import global_object_name


def is_retrying_enabled_on_request(request):
    return not bool(request.meta.get('dont_retry', False))


class RetryHandler(object):
    """utilities to handle retries"""

    def __init__(self, spider, request):
        self.spider = spider
        self.request = request
        self.max_retry_times = spider.settings.getint('RETRY_TIMES')
        self.priority_adjust = spider.settings.getint('RETRY_PRIORITY_ADJUST')

    def is_exhausted(self):
        """return whether current request has failed
           all allowed retry attempts"""
        max_retries = int(self.request.meta.get('max_retry_times', self.max_retry_times))
        retries = self.request.meta.get('retry_times', 0)
        return retries >= max_retries

    def make_retry_request(self):
        """create a new retrying request out of current request"""
        retries = self.request.meta.get('retry_times', 0) + 1
        retryreq = self.request.copy()
        retryreq.meta['retry_times'] = retries
        retryreq.dont_filter = True
        retryreq.priority = self.request.priority + self.priority_adjust
        return retryreq

    def record_retry(self, retry_request, reason):
        if isinstance(reason, Exception):
            reason = global_object_name(reason.__class__)

        stats = self.spider.crawler.stats
        retries = retry_request.meta.get('retry_times')
        self.spider.logger.debug(
            "Retrying %(request)s (failed %(retries)d times): %(reason)s",
            {'request': self.request, 'retries': retries, 'reason': reason},
            extra={'spider': self.spider}
        )
        stats.inc_value('retry/count')
        stats.inc_value('retry/reason_count/%s' % reason)

    def record_retry_failure(self, reason):
        if isinstance(reason, Exception):
            reason = global_object_name(reason.__class__)

        stats = self.spider.crawler.stats
        retries = self.request.meta.get('retry_times')
        stats.inc_value('retry/max_reached')
        self.spider.logger.debug(
            "Gave up retrying %(request)s (failed %(retries)d times): %(reason)s",
            {'request': self.request, 'retries': retries, 'reason': reason},
            extra={'spider': self.spider}
        )

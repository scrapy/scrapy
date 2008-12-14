"""
An extension to retry failed requests that are potentially caused by temporary
problems such as a connection timeout or HTTP 500 error.

You can change the behaviour of this moddileware by modifing the scraping settings: 
RETRY_TIMES - how many times to retry a failed page
RETRY_HTTP_CODES - which HTTP response codes to retry

Failed pages are collected on the scraping process and rescheduled at the end,
once the spider has finished crawling all regular (non failed) pages. Once
there is no more failed pages to retry this middleware sends a signal
(retry_complete), so other extensions could connect to that signal.

Default values are located in scrapy.conf.core_settings

About HTTP errors to consider:

- You may want to remove 400 from RETRY_HTTP_CODES, if you stick to the HTTP
  protocol. It's included by default because it's a common code used to
  indicate server overload, which would be something we want to retry
- 200 is included by default (and shoudln't be removed) to check for partial
  downloads errors, which means the TCP connection has broken in the middle of
  a HTTP download 
""" 

from twisted.internet.error import TimeoutError as ServerTimeoutError, DNSLookupError, \
                                   ConnectionRefusedError, ConnectionDone, ConnectError
from twisted.internet.defer import TimeoutError as UserTimeoutError 

from scrapy import log
from scrapy.core.exceptions import HttpException
from scrapy.stats import stats
from scrapy.conf import settings

class RetryMiddleware(object):

    EXCEPTIONS_TO_RETRY = (ServerTimeoutError, UserTimeoutError, DNSLookupError, 
                           ConnectionRefusedError, ConnectionDone, ConnectError)

    def __init__(self):
        self.failed_count = {}
        self.retry_times = settings.getint('RETRY_TIMES')
        self.retry_http_codes = map(int, settings.getlist('RETRY_HTTP_CODES'))

    def process_exception(self, request, exception, spider):
        if isinstance(exception, self.EXCEPTIONS_TO_RETRY) or (isinstance(exception, HttpException) and (int(exception.status) in self.retry_http_codes)):
            fp = request.fingerprint()
            self.failed_count[fp] = self.failed_count.get(fp, 0) + 1
            if isinstance(exception, self.EXCEPTIONS_TO_RETRY):
                exception_name = exception.__name__
                if exception_name == 'TimeoutError':
                    if 'defer' in str(exception):
                        exception_name = 'UserTimeoutError'
                    else:
                        exception_name = 'ServerTimeoutError'
                stats.incpath('%s/conn_error_count/%s' % (spider.domain_name, exception_name))
            else:
                stats.incpath('%s/http_error_count/%d' % (spider.domain_name, int(exception.status)))

            if self.failed_count[fp] <= self.retry_times:
                log.msg("Retrying %s (failed %d times): %s" % (request, self.failed_count[fp], exception), domain=spider.domain_name, level=log.DEBUG)
                retryreq = request.copy()
                retryreq.dont_filter = True
                return retryreq
            else:
                log.msg("Discarding %s (failed %d times): %s" % (request, self.failed_count[fp], exception), domain=spider.domain_name, level=log.DEBUG)


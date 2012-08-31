import os

from twisted.python.failure import Failure


SCRAPEDFMT = u"Scraped from %(src)s" + os.linesep + "%(item)s"
DROPPEDFMT = u"Dropped: %(exception)s" + os.linesep + "%(item)s"
CRAWLEDFMT = u"Crawled (%(status)s) %(request)s (referer: %(referer)s)%(flags)s"

class LogFormatter(object):
    """Class for generating log messages for different actions. All methods
    must return a plain string which doesn't include the log level or the
    timestamp
    """

    def crawled(self, request, response, spider):
        flags = ' %s' % str(response.flags) if response.flags else ''
        return {
            'format': CRAWLEDFMT,
            'status': response.status,
            'request': request,
            'referer': request.headers.get('Referer'),
            'flags': flags,
        }

    def scraped(self, item, response, spider):
        src = response.getErrorMessage() if isinstance(response, Failure) else response
        return {
            'format': SCRAPEDFMT,
            'src': src,
            'item': item,
        }

    def dropped(self, item, exception, response, spider):
        return {
            'format': DROPPEDFMT,
            'exception': exception,
            'item': item,
        }

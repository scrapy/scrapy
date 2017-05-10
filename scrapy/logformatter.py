import os
import logging

from twisted.python.failure import Failure

from scrapy.utils.request import referer_str

SCRAPEDMSG = u"Scraped from %(src)s" + os.linesep + "%(item)s"
DROPPEDMSG = u"Dropped: %(exception)s" + os.linesep + "%(item)s"
CRAWLEDMSG = u"Crawled (%(status)s) %(request)s%(request_flags)s (referer: %(referer)s)%(response_flags)s"


class LogFormatter(object):
    """Class for generating log messages for different actions.

    All methods must return a dictionary listing the parameters `level`, `msg`
    and `args` which are going to be used for constructing the log message when
    calling logging.log.

    Dictionary keys for the method outputs:
        * `level` should be the log level for that action, you can use those
        from the python logging library: logging.DEBUG, logging.INFO,
        logging.WARNING, logging.ERROR and logging.CRITICAL.

        * `msg` should be a string that can contain different formatting
        placeholders. This string, formatted with the provided `args`, is going
        to be the log message for that action.

        * `args` should be a tuple or dict with the formatting placeholders for
        `msg`.  The final log message is computed as output['msg'] %
        output['args'].
    """

    def crawled(self, request, response, spider):
        request_flags = ' %s' % str(request.flags) if request.flags else ''
        response_flags = ' %s' % str(response.flags) if response.flags else ''
        return {
            'level': logging.DEBUG,
            'msg': CRAWLEDMSG,
            'args': {
                'status': response.status,
                'request': request,
                'request_flags' : request_flags,
                'referer': referer_str(request),
                'response_flags': response_flags,
            }
        }

    def scraped(self, item, response, spider):
        if isinstance(response, Failure):
            src = response.getErrorMessage()
        else:
            src = response
        return {
            'level': logging.DEBUG,
            'msg': SCRAPEDMSG,
            'args': {
                'src': src,
                'item': item,
            }
        }

    def dropped(self, item, exception, response, spider):
        return {
            'level': logging.WARNING,
            'msg': DROPPEDMSG,
            'args': {
                'exception': exception,
                'item': item,
            }
        }

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

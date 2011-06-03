import os

class LogFormatter(object):
    """Class for generating log messages for different actions. All methods
    must return a plain string which doesn't include the log level or the
    timestamp
    """

    def crawled(self, request, response, spider):
        referer = request.headers.get('Referer')
        flags = ' %s' % str(response.flags) if response.flags else ''
        return "Crawled (%d) %s (referer: %s)%s" % (response.status, \
            request, referer, flags)

    def scraped(self, item, response, spider):
        return "Scraped from %s" % response + os.linesep + str(item)

    def dropped(self, item, exception, response, spider):
        return "Dropped: %s" % unicode(exception) + os.linesep + str(item)

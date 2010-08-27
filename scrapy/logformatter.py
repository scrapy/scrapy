
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

    def scraped(self, item, request, response, spider):
        return "Scraped %s in <%s>" % (item, request.url)

    def dropped(self, item, exception, spider):
        return "Dropped %s - %s" % (item, str(exception))

    def passed(self, item, spider):
        return "Passed %s" % item

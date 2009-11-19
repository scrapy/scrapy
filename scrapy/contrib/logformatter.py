"""Functions for logging diferent actions"""

def crawled_logline(request, response):
    referer = request.headers.get('Referer')
    flags = ' %s' % str(response.flags) if response.flags else ''
    return "Crawled (%d) %s (referer: %s)%s" % (response.status, \
        request, referer, flags)

class CommonMiddleware(object):
    """This middleware provides common/basic functionality, and should always
    be enabled"""

    def process_request(self, request, spider):
        request.headers.setdefault('Accept-Language', 'en')
        request.headers.setdefault('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
        if request.method == 'POST':
            request.headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')


from scrapy.http.request import Request
from scrapy.http.headers import Headers
class GiantFilesRequest(Request):
    '''
    most of the codes are the same as Request, but now I have changed several parts to fit the GiantFilesPipeline
    '''
    def __init__(self, url,store_path,callback=None, method='GET', headers=None, body=None,
                 cookies=None, meta=None, encoding='utf-8', priority=0,
                 dont_filter=False, errback=None,flags=None):

        self._encoding = encoding  # this one has to be set first
        self.method = str(method).upper()
        self._set_url(url)
        self._set_body(body)
        assert isinstance(priority, int), "Request priority not an integer: %r" % priority
        self.priority = priority
        self.store_path = store_path  #the FILES_STORE attribute in the SETTINSG
        assert callback or not errback, "Cannot use errback without a callback"
        self.callback = callback
        self.errback = errback

        self.cookies = cookies or {}
        self.headers = Headers(headers or {}, encoding=encoding)
        self.dont_filter = dont_filter

        self._meta = dict(meta) if meta else None
        self.flags = [] if flags is None else list(flags)
    def replace(self, *args, **kwargs):
        """Create a new GiantFileRequest with the same attributes except for those
        given new values.
        """
        for x in ['url','store_path', 'method', 'headers', 'body', 'cookies', 'meta',
                  'encoding', 'priority', 'dont_filter', 'callback', 'errback']:#added the store_path attribute here
            kwargs.setdefault(x, getattr(self, x))
        cls = kwargs.pop('cls', self.__class__)
        return cls(*args, **kwargs)


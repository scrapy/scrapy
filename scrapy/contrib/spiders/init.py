from scrapy.spider import BaseSpider

class InitSpider(BaseSpider):
    """Base Spider with initialization facilities"""
    
    def __init__(self, *a, **kw):
        super(InitSpider, self).__init__(*a, **kw)
        self._postinit_reqs = []
        self._init_complete = False
        self._init_started = False

    def make_requests_from_url(self, url):
        req = super(InitSpider, self).make_requests_from_url(url)
        if self._init_complete:
            return req
        self._postinit_reqs.append(req)
        if not self._init_started:
            self._init_started = True
            return self.init_request()

    def initialized(self, response=None):
        """This method must be set as the callback of your last initialization
        request. See self.init_request() docstring for more info.
        """
        self._init_complete = True
        reqs = self._postinit_reqs[:]
        del self._postinit_reqs
        return reqs

    def init_request(self):
        """This function should return one initialization request, with the
        self.initialized method as callback. When the self.initialized method
        is called this spider is considered initialized. If you need to perform
        several requests for initializing your spider, you can do so by using
        different callbacks. The only requirement is that the final callback
        (of the last initialization request) must be self.initialized. 
        
        The default implementation calls self.initialized immediately, and
        means that no initialization is needed. This method should be
        overridden only when you need to perform requests to initialize your
        spider
        """
        return self.initialized()


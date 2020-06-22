"""
HTTP basic auth downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from w3lib.http import basic_auth_header

from scrapy.http.response import Response
from scrapy import signals


class HttpAuthMiddleware:
    """Set Basic HTTP Authorization header
    (http_user and http_pass spider class attributes)"""

    @classmethod
    def from_crawler(cls, crawler):
        o = cls()   
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider):
        pass

    def _authenticated(self, response):
        if response.status == "401":
            return False

        return True

    def process_request(self, request, spider):
        if _authenticated(self, Response(request.url)):
            if request.url in spider.url_user_pwd.keys():
                usr = spider.url_user_pwd[request.url][0] #url_user_pwd is a dictionary of urls with their corresponding username, password
                pwd = spider.url_user_pwd[request.url][1]
                if usr or pwd:
                    self.auth = basic_auth_header(usr, pwd)

            auth = getattr(self, 'auth', None)
            request.headers[b'Authorization'] = auth

        # here redirect or retry middleware can be used if request needs authentication

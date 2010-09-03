from scrapy import optional_features
from scrapy.exceptions import NotConfigured
from scrapy.utils.httpobj import urlparse_cached
from scrapy.conf import settings
from .http import HttpRequestHandler


class S3RequestHandler(object):

    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None, \
            httprequesthandler=HttpRequestHandler):
        if 'boto' not in optional_features:
            raise NotConfigured("missing boto library")

        if not aws_access_key_id:
            aws_access_key_id = settings['AWS_ACCESS_KEY_ID']
        if not aws_secret_access_key:
            aws_secret_access_key = settings['AWS_SECRET_ACCESS_KEY']

        from boto import connect_s3
        try:
            self.conn = connect_s3(aws_access_key_id, aws_secret_access_key)
        except Exception, ex:
            raise NotConfigured(str(ex))
        self._download_http = httprequesthandler().download_request

    def download_request(self, request, spider):
        p = urlparse_cached(request)
        scheme = 'https' if request.meta.get('is_secure') else 'http'
        url = '%s://%s.s3.amazonaws.com%s' % (scheme, p.hostname, p.path)
        httpreq = request.replace(url=url)
        self.conn.add_aws_auth_header(httpreq.headers, httpreq.method, \
                '%s/%s' % (p.hostname, p.path))
        return self._download_http(httpreq, spider)

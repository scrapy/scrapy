from scrapy import optional_features
from scrapy.exceptions import NotConfigured
from scrapy.utils.httpobj import urlparse_cached
from .http import HTTPDownloadHandler

try:
    from boto.s3.connection import S3Connection
except ImportError:
    S3Connection = object

class _v19_S3Connection(S3Connection):
    """A dummy S3Connection wrapper that doesn't do any syncronous download"""
    def _mexe(self, method, bucket, key, headers, *args, **kwargs):
        return headers

class _v20_S3Connection(S3Connection):
    """A dummy S3Connection wrapper that doesn't do any syncronous download"""
    def _mexe(self, http_request, *args, **kwargs):
        http_request.authorize(connection=self)
        return http_request.headers

try:
    import boto.auth
except ImportError:
    _S3Connection = _v19_S3Connection
else:
    _S3Connection = _v20_S3Connection


class S3DownloadHandler(object):

    def __init__(self, settings, aws_access_key_id=None, aws_secret_access_key=None, \
            httpdownloadhandler=HTTPDownloadHandler):
        if 'boto' not in optional_features:
            raise NotConfigured("missing boto library")

        if not aws_access_key_id:
            aws_access_key_id = settings['AWS_ACCESS_KEY_ID']
        if not aws_secret_access_key:
            aws_secret_access_key = settings['AWS_SECRET_ACCESS_KEY']

        try:
            self.conn = _S3Connection(aws_access_key_id, aws_secret_access_key)
        except Exception as ex:
            raise NotConfigured(str(ex))
        self._download_http = httpdownloadhandler(settings).download_request

    def download_request(self, request, spider):
        p = urlparse_cached(request)
        scheme = 'https' if request.meta.get('is_secure') else 'http'
        bucket = p.hostname
        path = p.path + '?' + p.query if p.query else p.path
        url = '%s://%s.s3.amazonaws.com%s' % (scheme, bucket, path)
        signed_headers = self.conn.make_request(
                method=request.method,
                bucket=bucket,
                key=p.path,
                query_args=p.query,
                headers=request.headers,
                data=request.body)
        httpreq = request.replace(url=url, headers=signed_headers)
        return self._download_http(httpreq, spider)

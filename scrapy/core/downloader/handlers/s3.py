from six.moves.urllib.parse import unquote

from scrapy.exceptions import NotConfigured
from scrapy.utils.httpobj import urlparse_cached
from .http import HTTPDownloadHandler


def get_s3_connection():
    try:
        from boto.s3.connection import S3Connection
    except ImportError:
        return None

    class _v19_S3Connection(S3Connection):
        """A dummy S3Connection wrapper that doesn't do any synchronous download"""
        def _mexe(self, method, bucket, key, headers, *args, **kwargs):
            return headers

    class _v20_S3Connection(S3Connection):
        """A dummy S3Connection wrapper that doesn't do any synchronous download"""
        def _mexe(self, http_request, *args, **kwargs):
            http_request.authorize(connection=self)
            return http_request.headers

    try:
        import boto.auth
    except ImportError:
        _S3Connection = _v19_S3Connection
    else:
        _S3Connection = _v20_S3Connection

    return _S3Connection


class S3DownloadHandler(object):

    _conn = None

    def __init__(self, settings, aws_access_key_id=None, aws_secret_access_key=None,
            httpdownloadhandler=HTTPDownloadHandler):

        _S3Connection = get_s3_connection()
        if _S3Connection is None:
            raise NotConfigured("missing boto library")

        self.aws_access_key_id = aws_access_key_id or settings['AWS_ACCESS_KEY_ID']
        self.aws_secret_access_key = aws_secret_access_key or settings['AWS_SECRET_ACCESS_KEY']

        self._download_http = httpdownloadhandler(settings).download_request

    @property
    def conn(self):
        if self._conn is None:
            try:
                self._conn = _S3Connection(
                    self.aws_access_key_id,
                    self.aws_secret_access_key
                )
            except Exception as e:
                self._conn = e
                raise
        elif isinstance(self._conn, Exception):
            raise self._conn

        return self._conn

    def download_request(self, request, spider):
        p = urlparse_cached(request)
        scheme = 'https' if request.meta.get('is_secure') else 'http'
        bucket = p.hostname
        path = p.path + '?' + p.query if p.query else p.path
        url = '%s://%s.s3.amazonaws.com%s' % (scheme, bucket, path)
        signed_headers = self.conn.make_request(
                method=request.method,
                bucket=bucket,
                key=unquote(p.path),
                query_args=unquote(p.query),
                headers=request.headers,
                data=request.body)
        httpreq = request.replace(url=url, headers=signed_headers)
        return self._download_http(httpreq, spider)

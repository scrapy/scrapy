from six.moves.urllib.parse import unquote

from scrapy.exceptions import NotConfigured
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.datatypes import CaselessDict
from scrapy.utils.python import to_unicode
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
            # Py3 fix: headers are already converted to ascii in
            # S3DownloadHandler.download_request
            http_request._headers_quoted = True
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

    def __init__(self, settings, aws_access_key_id=None, aws_secret_access_key=None, \
            httpdownloadhandler=HTTPDownloadHandler, **kw):

        _S3Connection = get_s3_connection()
        if _S3Connection is None:
            raise NotConfigured("missing boto library")

        if not aws_access_key_id:
            aws_access_key_id = settings['AWS_ACCESS_KEY_ID']
        if not aws_secret_access_key:
            aws_secret_access_key = settings['AWS_SECRET_ACCESS_KEY']

        # If no credentials could be found anywhere,
        # consider this an anonymous connection request by default;
        # unless 'anon' was set explicitly (True/False).
        anon = kw.get('anon', None)
        if anon is None and not aws_access_key_id and not aws_secret_access_key:
            kw['anon'] = True

        try:
            self.conn = _S3Connection(aws_access_key_id, aws_secret_access_key, **kw)
        except Exception as ex:
            raise NotConfigured(str(ex))
        self._download_http = httpdownloadhandler(settings).download_request

    def download_request(self, request, spider):
        p = urlparse_cached(request)
        scheme = 'https' if request.meta.get('is_secure') else 'http'
        bucket = p.hostname
        path = p.path + '?' + p.query if p.query else p.path
        url = '%s://%s.s3.amazonaws.com%s' % (scheme, bucket, path)
        # boto headers are different from scrapy headers:
        # they expect unicode keys and values in python 3 and do not handle
        # multiple values.
        headers_to_sign = CaselessDict()
        for key, values in request.headers.items():
            value = b','.join(values)
            try:
                value = to_unicode(value, encoding='ascii')
                key = to_unicode(key, encoding='ascii')
            except UnicodeDecodeError:
                pass  # safe to skip as there are no non-ascii headers to sign
            else:
                headers_to_sign[key] = value
        signed_headers = self.conn.make_request(
                method=request.method,
                bucket=bucket,
                key=unquote(p.path),
                query_args=unquote(p.query),
                headers=headers_to_sign,
                data=request.body)
        headers = request.headers.copy()
        # Copy values changed in signed_headers.
        for k, v in signed_headers.items():
            if v != headers_to_sign.get(k):
                headers[k] = v
        httpreq = request.replace(url=url, headers=headers)
        return self._download_http(httpreq, spider)

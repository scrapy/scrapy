from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.exceptions import NotConfigured
from scrapy.utils.boto import is_botocore_available
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import create_instance


class S3DownloadHandler:

    def __init__(self, settings, *,
                 crawler=None,
                 aws_access_key_id=None, aws_secret_access_key=None,
                 aws_session_token=None,
                 httpdownloadhandler=HTTPDownloadHandler, **kw):
        if not is_botocore_available():
            raise NotConfigured('missing botocore library')

        if not aws_access_key_id:
            aws_access_key_id = settings['AWS_ACCESS_KEY_ID']
        if not aws_secret_access_key:
            aws_secret_access_key = settings['AWS_SECRET_ACCESS_KEY']
        if not aws_session_token:
            aws_session_token = settings['AWS_SESSION_TOKEN']

        self.anon = kw.pop('anon', None)
        if kw:
            raise TypeError(f'Unexpected keyword arguments: {kw}')

        self._signer = None
        import botocore.auth
        from botocore.credentials import Credentials
        from botocore.session import Session
        from botocore.exceptions import NoCredentialsError
        if not self.anon:
            # Follow credential creation logic in Session.create_client(),
            # which is used in item pipeline and feed exporter.
            if aws_access_key_id is not None and aws_secret_access_key is not None:
                credentials = Credentials(
                    access_key=aws_access_key_id,
                    secret_key=aws_secret_access_key,
                    token=aws_session_token,
                )
            else:
                credentials = Session().get_credentials()
            if credentials is not None:
                SignerCls = botocore.auth.AUTH_TYPE_MAPS['s3']
                self._signer = SignerCls(credentials)
            else:
                # If no credentials could be found anywhere,
                # consider this an anonymous connection request by default;
                # unless 'anon' was set explicitly (True/False).
                if self.anon is None:
                    self.anon = True
                else:
                    raise NoCredentialsError

        _http_handler = create_instance(
            objcls=httpdownloadhandler,
            settings=settings,
            crawler=crawler,
        )
        self._download_http = _http_handler.download_request

    @classmethod
    def from_crawler(cls, crawler, **kwargs):
        return cls(crawler.settings, crawler=crawler, **kwargs)

    def download_request(self, request, spider):
        p = urlparse_cached(request)
        scheme = 'https' if request.meta.get('is_secure') else 'http'
        bucket = p.hostname
        path = p.path + '?' + p.query if p.query else p.path
        url = f'{scheme}://{bucket}.s3.amazonaws.com{path}'
        if self.anon:
            request = request.replace(url=url)
        else:
            import botocore.awsrequest
            awsrequest = botocore.awsrequest.AWSRequest(
                method=request.method,
                url=f'{scheme}://s3.amazonaws.com/{bucket}{path}',
                headers=request.headers.to_unicode_dict(),
                data=request.body)
            self._signer.add_auth(awsrequest)
            request = request.replace(
                url=url, headers=awsrequest.headers.items())
        return self._download_http(request, spider)

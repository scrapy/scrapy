from urllib.parse import unquote, urlunparse

from scrapy.utils.httpobj import urlparse_cached


class UriUserinfoMiddleware(object):
    """Downloader middleware that replaces `URI userinfo`_ data (user credentials
    for HTTP or FTP specified in the request URL) with the corresponding meta
    keys for later middlewares or download handlers to use them for
    authentication.

    It sets:

    -   :reqmeta:`ftp_user` and :reqmeta:`ftp_password` for FTP requests

    -   :reqmeta:`http_user` and :reqmeta:`http_pass` for HTTP and HTTPS
        requests

    .. _URI userinfo: https://tools.ietf.org/html/rfc2396.html#section-3.2.2
    """

    def process_request(self, request, spider):
        parsed_url = urlparse_cached(request)
        if parsed_url.username is None and parsed_url.password is None:
            return

        if parsed_url.scheme.startswith('http'):
            username_field, password_field = 'http_user', 'http_pass'
        elif parsed_url.scheme.startswith('ftp'):
            username_field, password_field = 'ftp_user', 'ftp_password'
        else:
            return

        for key, value in ((username_field, parsed_url.username),
                           (password_field, parsed_url.password)):
            if value is not None:
                request.meta.setdefault(key, unquote(value))

        userinfoless_url = urlunparse(
            (
                parsed_url.scheme,
                parsed_url.netloc.split('@')[-1],
                parsed_url.path,
                parsed_url.params,
                parsed_url.query,
                parsed_url.fragment,
            )
        )
        return request.replace(url=userinfoless_url)

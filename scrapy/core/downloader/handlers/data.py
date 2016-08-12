import base64
import re

import six

if six.PY2:
    from urllib import unquote
else:
    from urllib.parse import unquote_to_bytes as unquote

from scrapy.http import TextResponse
from scrapy.responsetypes import responsetypes
from scrapy.utils.datatypes import CaselessDict
from scrapy.utils.decorators import defers


# ASCII characters.
_char = set(map(chr, range(127)))

# RFC 2045 token.
_token = r'[{}]+'.format(re.escape(''.join(_char -
                                           # Control characters.
                                           set(map(chr, range(0, 32))) -
                                           # tspecials and space.
                                           set('()<>@,;:\\"/[]?= '))))

# RFC 822 quoted-string, without surrounding quotation marks.
_quoted_string = r'(?:[{}]|(?:\\[{}]))*'.format(
    re.escape(''.join(_char - {'"', '\\', '\r'})),
    re.escape(''.join(_char))
)

# Encode the regular expression strings to make them into bytes, as Python 3
# bytes have no format() method, but bytes must be passed to re.compile() in
# order to make a pattern object that can be used to match on bytes.

# RFC 2397 mediatype.
_mediatype_pattern = re.compile(
    r'{token}/{token}'.format(token=_token).encode()
)

_mediatype_parameter_pattern = re.compile(
    r';({token})=(?:({token})|"({quoted})")'.format(token=_token,
                                                    quoted=_quoted_string
                                                    ).encode()
)


class DataURIDownloadHandler(object):
    def __init__(self, settings):
        super(DataURIDownloadHandler, self).__init__()

    @defers
    def download_request(self, request, spider):
        url = request.url

        scheme, url = url.split(':', 1)
        if scheme != 'data':
            raise ValueError("not a data URI")

        # RFC 3986 section 2.1 allows percent encoding to escape characters
        # that would be interpreted as delimiters, implying that actual
        # delimiters should not be percent-encoded.
        # Decoding before parsing will allow malformed URIs with
        # percent-encoded delimiters, but it makes parsing easier and should
        # not affect well-formed URIs, as the delimiters used in this URI
        # scheme are not allowed, percent-encoded or not, in tokens.
        url = unquote(url)

        media_type = "text/plain"
        media_type_params = CaselessDict()

        m = _mediatype_pattern.match(url)
        if m:
            media_type = m.group().decode()
            url = url[m.end():]
        else:
            media_type_params['charset'] = "US-ASCII"

        while True:
            m = _mediatype_parameter_pattern.match(url)
            if m:
                attribute, value, value_quoted = m.groups()
                if value_quoted:
                    value = re.sub(br'\\(.)', r'\1', value_quoted)
                media_type_params[attribute.decode()] = value.decode()
                url = url[m.end():]
            else:
                break

        is_base64, data = url.split(b',', 1)
        if is_base64:
            if is_base64 != b";base64":
                raise ValueError("invalid data URI")
            data = base64.b64decode(data)

        respcls = responsetypes.from_mimetype(media_type)

        resp_kwargs = {}

        if media_type:
            media_type = media_type.split('/')
            if issubclass(respcls, TextResponse) and media_type[0] == 'text':
                resp_kwargs['encoding'] = media_type_params.get('charset')

        return respcls(url=request.url, body=data, **resp_kwargs)

import warnings
import six
if six.PY2:
    from cStringIO import StringIO as BytesIO
else:
    from io import BytesIO
from w3lib.util import unicode_to_str


def encode_multipart(data):
    r"""

    .. warning::

        This function is deprecated and will be removed in future.
        Please use ``urllib3.filepost.encode_multipart_formdata`` instead.

    Encode the given data to be used in a multipart HTTP POST.

    `data` is a dictionary where keys are the field name, and values are
    either strings or tuples as `(filename, content)` for file uploads.

    This code is based on :class:`distutils.command.upload`.

    Returns a `(body, boundary)` tuple where `body` is binary body value,
    and `boundary` is the boundary used (as native string).

    >>> import w3lib.form
    >>> w3lib.form.encode_multipart({'key': 'value'})
    ('\r\n----------------GHSKFJDLGDS7543FJKLFHRE75642756743254\r\nContent-Disposition: form-data; name="key"\r\n\r\nvalue\r\n----------------GHSKFJDLGDS7543FJKLFHRE75642756743254--\r\n', '--------------GHSKFJDLGDS7543FJKLFHRE75642756743254')
    >>> w3lib.form.encode_multipart({'key1': 'value1', 'key2': 'value2'})   # doctest: +SKIP
    ('\r\n----------------GHSKFJDLGDS7543FJKLFHRE75642756743254\r\nContent-Disposition: form-data; name="key2"\r\n\r\nvalue2\r\n----------------GHSKFJDLGDS7543FJKLFHRE75642756743254\r\nContent-Disposition: form-data; name="key1"\r\n\r\nvalue1\r\n----------------GHSKFJDLGDS7543FJKLFHRE75642756743254--\r\n', '--------------GHSKFJDLGDS7543FJKLFHRE75642756743254')
    >>> w3lib.form.encode_multipart({'somekey': ('path/to/filename', b'\xa1\xa2\xa3\xa4\r\n\r')})
    ('\r\n----------------GHSKFJDLGDS7543FJKLFHRE75642756743254\r\nContent-Disposition: form-data; name="somekey"; filename="path/to/filename"\r\n\r\n\xa1\xa2\xa3\xa4\r\n\r\r\n----------------GHSKFJDLGDS7543FJKLFHRE75642756743254--\r\n', '--------------GHSKFJDLGDS7543FJKLFHRE75642756743254')
    >>>

    """

    warnings.warn(
        "`w3lib.form.encode_multipart` function is deprecated and "
        "will be removed in future releases. Please use "
        "`urllib3.filepost.encode_multipart_formdata` instead.",
        DeprecationWarning
    )

    # Build up the MIME payload for the POST data
    boundary = '--------------GHSKFJDLGDS7543FJKLFHRE75642756743254'
    sep_boundary = b'\r\n--' + boundary.encode('ascii')
    end_boundary = sep_boundary + b'--'
    body = BytesIO()
    for key, value in data.items():
        title = u'\r\nContent-Disposition: form-data; name="%s"' % key
        # handle multiple entries for the same name
        if type(value) != type([]):
            value = [value]
        for value in value:
            if type(value) is tuple:
                title += u'; filename="%s"' % value[0]
                value = value[1]
            else:
                value = unicode_to_str(value)  # in distutils: str(value).encode('utf-8')
            body.write(sep_boundary)
            body.write(title.encode('utf-8'))
            body.write(b"\r\n\r\n")
            body.write(value)
    body.write(end_boundary)
    body.write(b"\r\n")
    return body.getvalue(), boundary

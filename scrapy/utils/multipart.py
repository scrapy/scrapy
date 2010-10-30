from cStringIO import StringIO

def encode_multipart(data):
    """Encode the given data to be used in a multipart HTTP POST. Data is a
    where keys are the field name, and values are either strings or tuples
    (filename, content) for file uploads.

    This code is based on distutils.command.upload
    """

    # Build up the MIME payload for the POST data
    boundary = '--------------GHSKFJDLGDS7543FJKLFHRE75642756743254'
    sep_boundary = '\r\n--' + boundary
    end_boundary = sep_boundary + '--'
    body = StringIO()
    for key, value in data.items():
        # handle multiple entries for the same name
        if type(value) != type([]):
            value = [value]
        for value in value:
            if type(value) is tuple:
                fn = '; filename="%s"' % value[0]
                value = value[1]
            else:
                fn = ""

            body.write(sep_boundary)
            body.write('\r\nContent-Disposition: form-data; name="%s"' % key)
            body.write(fn)
            body.write("\r\n\r\n")
            body.write(value)
    body.write(end_boundary)
    body.write("\r\n")
    return body.getvalue(), boundary

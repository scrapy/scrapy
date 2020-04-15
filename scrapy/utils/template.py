"""Helper functions for working with templates"""

import os
import re
import string


def render_templatefile(path, **kwargs):
    with open(path, 'rb') as fp:
        raw = fp.read().decode('utf8')

    content = string.Template(raw).substitute(**kwargs)

    render_path = path[:-len('.tmpl')] if path.endswith('.tmpl') else path
    with open(render_path, 'wb') as fp:
        fp.write(content.encode('utf8'))
    if path.endswith('.tmpl'):
        os.remove(path)


CAMELCASE_INVALID_CHARS = re.compile(r'[^a-zA-Z\d]')


def string_camelcase(string):
    """ Convert a word  to its CamelCase version and remove invalid chars

    >>> string_camelcase('lost-pound')
    'LostPound'

    >>> string_camelcase('missing_images')
    'MissingImages'

    """
    return CAMELCASE_INVALID_CHARS.sub('', string.title())

"""Helper functions for working with templates"""

import re
import string


def render_templatefile(path, **kwargs):
    raw = path.read_text(encoding='utf8')

    content = string.Template(raw).substitute(**kwargs)

    render_path = path.with_suffix('')

    if path.suffix == '.tmpl':
        path.rename(path, render_path)

    render_path.write_text(content, encoding='utf8')


CAMELCASE_INVALID_CHARS = re.compile(r'[^a-zA-Z\d]')


def string_camelcase(string):
    """ Convert a word  to its CamelCase version and remove invalid chars

    >>> string_camelcase('lost-pound')
    'LostPound'

    >>> string_camelcase('missing_images')
    'MissingImages'

    """
    return CAMELCASE_INVALID_CHARS.sub('', string.title())

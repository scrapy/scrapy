"""Helper functions for working with templates"""

import re
import string
from pathlib import Path


def render_templatefile(path: str, **kwargs):
    raw = Path(path).read_text('utf8')

    content = string.Template(raw).substitute(**kwargs)

    render_path = path[:-len('.tmpl')] if path.endswith('.tmpl') else path

    if path.endswith('.tmpl'):
        Path(path).rename(render_path)

    Path(render_path).write_text(content, 'utf8')


CAMELCASE_INVALID_CHARS = re.compile(r'[^a-zA-Z\d]')


def string_camelcase(string):
    """ Convert a word  to its CamelCase version and remove invalid chars

    >>> string_camelcase('lost-pound')
    'LostPound'

    >>> string_camelcase('missing_images')
    'MissingImages'

    """
    return CAMELCASE_INVALID_CHARS.sub('', string.title())

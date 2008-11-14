import re
from scrapy.utils.markup import replace_tags, remove_entities

def remove_tags(value):
    """
    Removes any tags found in each of the provided list's string.
    E.g:
      >> remove_tags(['<head>my header</head>', '<body>my <b>body</b></body>'])
      [u'my header', u'my body']
    Input: iterable with strings
    Output: list of unicodes
    """
    return [ replace_tags(v) for v in value ]

def remove_root(value):
    """
    Input: iterable with strings
    Output: list of strings
    """
    def _remove_root(value):
        _remove_root_re = re.compile(r'^\s*<.*?>(.*)</.*>\s*$', re.DOTALL)
        m = _remove_root_re.search(value)
        if m:
            value = m.group(1)
        return unicode(value)
    return [ _remove_root(v) for v in value ]

class Unquote(object):
    """
    Receives a list of strings, removes all of the
    entities the strings may have, and returns
    a new list

    Input: iterable with strings
    Output: list of strings
    """
    def __init__(self, keep=['lt', 'amp']):
        self.keep = keep

    def __call__(self, value):
        return [ remove_entities(v, keep=self.keep) for v in value ]



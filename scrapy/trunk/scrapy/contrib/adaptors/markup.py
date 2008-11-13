import re
from scrapy.utils.markup import replace_tags, remove_entities

def remove_tags(value):
    """
    Input: iterable with strings
    Output: list of strings
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
        return value
    return [ _remove_root(v) for v in value ]

def unquote(value, keep_entities=None):
    """
    Receives a list of strings, removes all of the
    entities the strings may have, and returns
    a new list

    Input: iterable with strings
    Output: list of strings
    """
    if keep_entities is None:
        keep_entities = ['lt', 'amp']
    return [ remove_entities(v, keep=keep_entities) for v in value ]



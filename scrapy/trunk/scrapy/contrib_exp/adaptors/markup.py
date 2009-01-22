import re
from scrapy.utils.markup import replace_tags, unquote_markup
from scrapy.utils.python import str_to_unicode
from scrapy.item.adaptors import adaptize

def remove_tags(value):
    """
    Removes any tags found in each of the provided list's string.
    E.g:
      >> remove_tags('<head>my header</head>', '<body>my <b>body</b></body>')
      u'my header', u'my body'
    Input: string/unicode
    Output: unicode
    """
    return replace_tags(value)

_remove_root_re = re.compile(r'^\s*<.*?>(.*)</.*>\s*$', re.DOTALL)
def remove_root(value):
    """
    Input: string/unicode
    Output: unicode
    """
    m = _remove_root_re.search(value)
    if m:
        value = m.group(1)
    return str_to_unicode(value)

class Unquote(object):
    """
    Receives a list of strings, removes all of the
    CDATAs and entities (except the ones in CDATAs) the strings
    may have, and returns a new list.

    Input: string/unicode
    Output: string/unicode
    """
    def __init__(self, keep=None):
        self.keep = [] if keep is None else keep

    def __call__(self, value, adaptor_args):
        keep = adaptor_args.get('keep_entities', self.keep)
        return unquote_markup(value, keep=keep)

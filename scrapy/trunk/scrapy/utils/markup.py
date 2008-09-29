"""
Functions for dealing with markup text
"""

import re
import htmlentitydefs

_ent_re = re.compile(r'&(#?)([^&;]+);')
_tag_re = re.compile(r'<[a-zA-Z\/!].*?>', re.DOTALL)

def remove_entities(text, keep=(), remove_illegal=True):
    """Remove entities from the given text.

    'text' can be a unicode string or a regular string encoded as 'utf-8'

    If 'keep' is passed (with a list of entity names) those entities will
    be kept (they won't be removed).

    It supports both numeric (&#nnnn;) and named (&nbsp; &gt;) entities.

    If remove_illegal is True, entities that can't be converted are removed.
    If remove_illegal is False, entities that can't be converted are kept "as
    is". For more information see the tests.

    Always returns a unicode string (with the entities removed).
    """

    def convert_entity(m):
        if m.group(1) == '#':
            try:
                return unichr(int(m.group(2)))
            except ValueError:
                if remove_illegal:
                    return u''
                else:
                    return u'&#%s;' % m.group(2)
        try:
            if m.group(2) in keep:
                return '&%s;' % m.group(2)
            else:
                return unichr(htmlentitydefs.name2codepoint[m.group(2)])
        except KeyError:
            if remove_illegal:
                return u''
            else:
                return u'&%s;' % m.group(2)

    return _ent_re.sub(convert_entity, text.decode('utf-8'))

def has_entities(text):
    return bool(_ent_re.search(text))

def replace_tags(text, token=''):
    """Replace all markup tags found in the given text by the given token. By
    default token is a null string so it just remove all tags.

    'text' can be a unicode string or a regular string encoded as 'utf-8'

    Always returns a unicode string.
    """
    return _tag_re.sub(token, text.decode('utf-8'))

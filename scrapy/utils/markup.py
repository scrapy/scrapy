"""
Functions for dealing with markup text
"""

import re
from htmlentitydefs import name2codepoint

from scrapy.utils.python import str_to_unicode

_ent_re = re.compile(r'&(#?(x?))([^&;\s]+);')
_tag_re = re.compile(r'<[a-zA-Z\/!].*?>', re.DOTALL)

def remove_entities(text, keep=(), remove_illegal=True, encoding='utf-8'):
    """Remove entities from the given text.

    'text' can be a unicode string or a regular string encoded in the given
    `encoding` (which defaults to 'utf-8').

    If 'keep' is passed (with a list of entity names) those entities will
    be kept (they won't be removed).

    It supports both numeric (&#nnnn; and &#hhhh;) and named (&nbsp; &gt;)
    entities.

    If remove_illegal is True, entities that can't be converted are removed.
    If remove_illegal is False, entities that can't be converted are kept "as
    is". For more information see the tests.

    Always returns a unicode string (with the entities removed).
    """

    def convert_entity(m):
        entity_body = m.group(3)
        if m.group(1):
            try:
                if m.group(2):
                    number = int(entity_body, 16)
                else:
                    number = int(entity_body, 10)
                # Numeric character references in the 80-9F range are typically
                # interpreted by browsers as representing the characters mapped
                # to bytes 80-9F in the Windows-1252 encoding. For more info
                # see: http://en.wikipedia.org/wiki/Character_encodings_in_HTML
                if 0x80 <= number <= 0x9f:
                    return chr(number).decode('cp1252')
            except ValueError:
                number = None
        else:
            if entity_body in keep:
                return m.group(0)
            else:
                number = name2codepoint.get(entity_body)
        if number is not None:
            try:
                return unichr(number)
            except ValueError:
                pass

        return u'' if remove_illegal else m.group(0)

    return _ent_re.sub(convert_entity, str_to_unicode(text, encoding))

def has_entities(text, encoding=None):
    return bool(_ent_re.search(str_to_unicode(text, encoding)))

def replace_tags(text, token='', encoding=None):
    """Replace all markup tags found in the given text by the given token. By
    default token is a null string so it just remove all tags.

    'text' can be a unicode string or a regular string encoded as 'utf-8'

    Always returns a unicode string.
    """
    return _tag_re.sub(token, str_to_unicode(text, encoding))


def remove_comments(text, encoding=None):
    """ Remove HTML Comments. """
    return re.sub('<!--.*?-->', u'', str_to_unicode(text, encoding), re.DOTALL)
      
def remove_tags(text, which_ones=(), keep=(), encoding=None):
    """ Remove HTML Tags only. 

        which_ones and keep are both tuples, there are four cases:

        which_ones, keep (1 - not empty, 0 - empty)
        1, 0 - remove all tags in which_ones
        0, 1 - remove all tags except the ones in keep
        0, 0 - remove all tags
        1, 1 - not allowd
    """

    assert not (which_ones and keep), 'which_ones and keep can not be given at the same time'

    def will_remove(tag):
        if which_ones:
            return tag in which_ones
        else:
            return tag not in keep

    def remove_tag(m):
        tag = m.group(1)
        return u'' if will_remove(tag) else m.group(0)

    regex = '</?([^ >/]+).*?>'
    retags = re.compile(regex, re.DOTALL | re.IGNORECASE)

    return retags.sub(remove_tag, str_to_unicode(text, encoding))

def remove_tags_with_content(text, which_ones=(), encoding=None):
    """ Remove tags and its content.
        
        which_ones -- is a tuple of which tags with its content we want to remove.
                      if is empty do nothing.
    """
    text = str_to_unicode(text, encoding)
    if which_ones:
        tags = '|'.join([r'<%s.*?</%s>|<%s\s*/>' % (tag, tag, tag) for tag in which_ones])
        retags = re.compile(tags, re.DOTALL | re.IGNORECASE)
        text = retags.sub(u'', text)
    return text
    

def replace_escape_chars(text, which_ones=('\n', '\t', '\r'), replace_by=u'', \
        encoding=None):
    """ Remove escape chars. Default : \\n, \\t, \\r

        which_ones -- is a tuple of which escape chars we want to remove.
                      By default removes \n, \t, \r.

        replace_by -- text to replace the escape chars for.
                      It defaults to '', so the escape chars are removed.
    """
    for ec in which_ones:
        text = text.replace(ec, str_to_unicode(replace_by, encoding))
    return str_to_unicode(text, encoding)

def unquote_markup(text, keep=(), remove_illegal=True, encoding=None):
    """
    This function receives markup as a text (always a unicode string or a utf-8 encoded string) and does the following:
     - removes entities (except the ones in 'keep') from any part of it that it's not inside a CDATA
     - searches for CDATAs and extracts their text (if any) without modifying it.
     - removes the found CDATAs
    """
    _cdata_re = re.compile(r'((?P<cdata_s><!\[CDATA\[)(?P<cdata_d>.*?)(?P<cdata_e>\]\]>))', re.DOTALL)

    def _get_fragments(txt, pattern):
        offset = 0
        for match in pattern.finditer(txt):
            match_s, match_e = match.span(1)
            yield txt[offset:match_s]
            yield match
            offset = match_e
        yield txt[offset:]

    text = str_to_unicode(text, encoding)
    ret_text = u''
    for fragment in _get_fragments(text, _cdata_re):
        if isinstance(fragment, basestring):
            # it's not a CDATA (so we try to remove its entities)
            ret_text += remove_entities(fragment, keep=keep, remove_illegal=remove_illegal)
        else:
            # it's a CDATA (so we just extract its content)
            ret_text += fragment.group('cdata_d')
    return ret_text

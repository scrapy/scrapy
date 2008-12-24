"""
Functions for dealing with markup text
"""

import re
import htmlentitydefs

from scrapy.utils.python import str_to_unicode

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

    return _ent_re.sub(convert_entity, str_to_unicode(text))

def has_entities(text):
    return bool(_ent_re.search(str_to_unicode(text)))

def replace_tags(text, token=''):
    """Replace all markup tags found in the given text by the given token. By
    default token is a null string so it just remove all tags.

    'text' can be a unicode string or a regular string encoded as 'utf-8'

    Always returns a unicode string.
    """
    return _tag_re.sub(token, str_to_unicode(text))


def remove_comments(text):
    """ Remove HTML Comments. """
    return re.sub('<!--.*?-->', u'', str_to_unicode(text), re.DOTALL)
      
def remove_tags(text, which_ones=()):
    """ Remove HTML Tags only. 

        which_ones -- is a tuple of which tags we want to remove.
                      if is empty remove all tags.
    """
    if len(which_ones) > 0:
        tags = [ '<%s>|<%s .*?>|</%s>' % (tag,tag,tag) for tag in which_ones ]
        reg_exp_remove_tags = '|'.join(tags)
    else:
        reg_exp_remove_tags = '<.*?>'
    re_tags = re.compile(reg_exp_remove_tags, re.DOTALL)
    return re_tags.sub(u'', str_to_unicode(text))

def remove_tags_with_content(text, which_ones=()):
    """ Remove tags and its content.
        
        which_ones -- is a tuple of which tags with its content we want to remove.
                      if is empty do nothing.
    """
    tags = [ '<%s.*?</%s>' % (tag,tag) for tag in which_ones ]
    re_tags_remove = re.compile('|'.join(tags), re.DOTALL)
    return re_tags_remove.sub(u'', str_to_unicode(text))

def remove_escape_chars(text, which_ones=('\n','\t','\r')):
    """ Remove escape chars. Default : \\n, \\t, \\r

        which_ones -- is a tuple of which escape chars we want to remove.
                      By default removes \n, \t, \r.
    """
    re_escape_chars = re.compile('[%s]' % ''.join(which_ones))
    return re_escape_chars.sub(u'', str_to_unicode(text))

def unquote_markup(text, keep=(), remove_illegal=True):
    """
    This function receives markup as a text (always a unicode string or a utf-8 encoded string) and does the following:
     - removes entities (except the ones in 'keep') from any part of it that it's not inside a CDATA
     - searches for CDATAs and extracts their text (if any) without modifying it.
     - removes the found CDATAs
    """
    _cdata_re = re.compile(r'((?P<cdata_s><!\[CDATA\[)(?P<cdata_d>.*?)(?P<cdata_e>\]\]>))', re.DOTALL)

    def _get_fragments(txt, pattern):
        fragments = []
        offset = 0
        for match in pattern.finditer(txt):
            match_s, match_e = match.span(1)
            fragments.append(txt[offset:match_s])
            fragments.append(match)
            offset = match_e
        fragments.append(txt[offset:])
        return fragments

    text = str_to_unicode(text)
    ret_text = u''
    for fragment in _get_fragments(text, _cdata_re):
        if isinstance(fragment, basestring):
            # it's not a CDATA (so we try to remove its entities)
            ret_text += remove_entities(fragment, keep=keep, remove_illegal=remove_illegal)
        else:
            # it's a CDATA (so we just extract its content)
            ret_text += fragment.group('cdata_d')
    return ret_text

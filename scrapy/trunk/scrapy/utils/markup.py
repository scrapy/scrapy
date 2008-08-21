"""
Functions for dealing with markup text
"""

import re
import htmlentitydefs

_ent_re = re.compile(r'&(#?)(.+?);')
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
        if m.group(1)=='#':
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


def replace_tags(text, token=''):
    """Replace all markup tags found in the given text by the given token. By
    default token is a null string so it just remove all tags.

    'text' can be a unicode string or a regular string encoded as 'utf-8'

    Always returns a unicode string.
    """
    return _tag_re.sub(token, text.decode('utf-8'))

_clean_spaces_re = re.compile("\s+", re.U)
_remove_root_re = re.compile(r'^\s*<.*?>(.*)</.*>\s*$', re.DOTALL)
_xml_remove_tags_re = re.compile(r'<[a-zA-Z\/!][^>]*?>')
_xml_remove_cdata_re = re.compile('<!\[CDATA\[(.*)\]\]', re.S)
_xml_cdata_split_re = re.compile('(<!\[CDATA\[.*?\]\]>)', re.S)

def remove_tags(xml, **kwargs):
    if kwargs.get('remove_tags', True):
        xml = _xml_remove_tags_re.sub(' ', xml)
    return xml

def xml_remove_tags(xml, **kwargs):
    #process in pieces the text that contains CDATA. The first check is to avoid unnecesary regex check
    if _xml_remove_cdata_re.search(xml):
        pieces = []
        
        for piece in _xml_cdata_split_re.split(xml):
            
            m = _xml_remove_cdata_re.search(piece)
            if m:
                if kwargs.get('remove_cdata', True):#remove cdata special tag
                    pieces.append(remove_tags(m.groups()[0], **kwargs))
                else:
                    pieces.append(piece)#conserve intact the cdata
            else:
                pieces.append(remove_tags(piece, **kwargs))

        xml = "".join(pieces)
    else:
        xml = remove_tags(xml, **kwargs)
    return xml


def clean_markup(string, **kwargs):
    """Clean (list of) strings removing newlines, spaces, etc"""
    
    _remove_tags = xml_remove_tags if kwargs.get("xml_doc") else remove_tags

    if isinstance(string, list):
        return [clean_markup(s, **kwargs) for s in string]
    
    string = _remove_tags(string, **kwargs)

    if kwargs.get('remove_root', True) and not kwargs.get('remove_tags', True):
        m = _remove_root_re.search(string)
        if m:
            string = m.group(1)

    if kwargs.get('remove_spaces', True):
        string = _clean_spaces_re.sub(' ', string)
    if kwargs.get('strip', True):
        string = string.strip()

    return string

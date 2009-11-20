"""
This module provides functions for generating libxml2 documents (xmlDoc).

Constructors must receive a Response object and return a xmlDoc object.
"""

import libxml2

xml_parser_options = libxml2.XML_PARSE_RECOVER + \
                     libxml2.XML_PARSE_NOERROR + \
                     libxml2.XML_PARSE_NOWARNING

html_parser_options = libxml2.HTML_PARSE_RECOVER + \
                      libxml2.HTML_PARSE_NOERROR + \
                      libxml2.HTML_PARSE_NOWARNING

utf8_encodings = set(('utf-8', 'UTF-8', 'utf8', 'UTF8'))

def body_as_utf8(response):
    if response.encoding in utf8_encodings:
        return response.body
    else:
        return response.body_as_unicode().encode('utf-8')
        
def xmlDoc_from_html(response):
    """Return libxml2 doc for HTMLs"""
    utf8body = body_as_utf8(response) or ' '
    try:
        lxdoc = libxml2.htmlReadDoc(utf8body, response.url, 'utf-8', \
            html_parser_options)
    except TypeError:  # libxml2 doesn't parse text with null bytes
        lxdoc = libxml2.htmlReadDoc(utf8body.replace("\x00", ""), response.url, \
            'utf-8', html_parser_options)
    return lxdoc

def xmlDoc_from_xml(response):
    """Return libxml2 doc for XMLs"""
    utf8body = body_as_utf8(response) or ' '
    try:
        lxdoc = libxml2.readDoc(utf8body, response.url, 'utf-8', \
            xml_parser_options)
    except TypeError:  # libxml2 doesn't parse text with null bytes
        lxdoc = libxml2.readDoc(utf8body.replace("\x00", ""), response.url, \
            'utf-8', xml_parser_options)
    return lxdoc

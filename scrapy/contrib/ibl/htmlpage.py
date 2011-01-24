"""
htmlpage

Container object for representing html pages in the IBL system. This
encapsulates page related information and prevents parsing multiple times.
"""
import re
import hashlib

from scrapy.utils.python import str_to_unicode

def create_page_from_jsonpage(jsonpage, body_key):
    """Create an HtmlPage object from a dict object conforming to the schema
    for a page

    `body_key` is the key where the body is stored and can be either 'body'
    (original page with annotations - if any) or 'original_body' (original
    page, always). Classification typically uses 'original_body' to avoid
    confusing the classifier with annotated pages, while extraction uses 'body'
    to pass the annotated pages.
    """
    url = jsonpage['url']
    headers = jsonpage.get('headers')
    body = str_to_unicode(jsonpage[body_key])
    page_id = jsonpage.get('page_id')
    return HtmlPage(url, headers, body, page_id)

class HtmlPage(object):
    def __init__(self, url=None, headers=None, body=None, page_id=None):
        assert isinstance(body, unicode), "unicode expected, got: %s" % type(body).__name__
        self.headers = headers or {}
        self.body = body
        self.url = url or u''
        if page_id is None and url:
            self.page_id = hashlib.sha1(url).hexdigest()
        else:
            self.page_id = page_id 
    

    def _set_body(self, body):
        self._body = body
        self.parsed_body = list(parse_html(body))
        
    body = property(lambda x: x._body, _set_body)
    
    def fragment_data(self, data_fragment):
        return self.body[data_fragment.start:data_fragment.end]
    
class HtmlTagType(object):
    OPEN_TAG = 1
    CLOSE_TAG = 2 
    UNPAIRED_TAG = 3

class HtmlDataFragment(object):
    __slots__ = ('start', 'end')
    
    def __init__(self, start, end):
        self.start = start
        self.end = end
        
    def __str__(self):
        return "<HtmlDataFragment [%s:%s]>" % (self.start, self.end)

    def __repr__(self):
        return str(self)
    
class HtmlTag(HtmlDataFragment):
    __slots__ = ('tag_type', 'tag', 'attributes')

    def __init__(self, tag_type, tag, attributes, start, end):
        HtmlDataFragment.__init__(self, start, end)
        self.tag_type = tag_type
        self.tag = tag
        self.attributes = attributes

    def __str__(self):
        return "<HtmlTag tag='%s' attributes={%s} [%s:%s]>" % (self.tag, ', '.join(sorted\
                (["%s: %s" % (k, repr(v)) for k, v in self.attributes.items()])), self.start, self.end)
    
    def __repr__(self):
        return str(self)

_ATTR = "((?:[^=/<>\s]|/(?!>))+)(?:\s*=(?:\s*\"(.*?)\"|\s*'(.*?)'|([^>\s]+))?)?"
_TAG = "<(\/?)(\w+(?::\w+)?)((?:\s*" + _ATTR + ")+\s*|\s*)(\/?)>?"
_DOCTYPE = r"<!DOCTYPE.*?>"
_SCRIPT = "(<script.*?>)(.*?)(</script.*?>)"
_COMMENT = "(<!--.*?-->)"

_ATTR_REGEXP = re.compile(_ATTR, re.I | re.DOTALL)
_HTML_REGEXP = re.compile("%s|%s|%s" % (_COMMENT, _SCRIPT, _TAG), re.I | re.DOTALL)
_DOCTYPE_REGEXP = re.compile("(?:%s)" % _DOCTYPE)
_COMMENT_REGEXP = re.compile(_COMMENT, re.DOTALL)

def parse_html(text):
    """Higher level html parser. Calls lower level parsers and joins sucesive
    HtmlDataFragment elements in a single one.
    """
    # If have doctype remove it.
    start_pos = 0
    match = _DOCTYPE_REGEXP.match(text)
    if match:
        start_pos = match.end()
    prev_end = start_pos
    for match in _HTML_REGEXP.finditer(text, start_pos):
        start = match.start()
        end = match.end()
            
        if start > prev_end:
            yield HtmlDataFragment(prev_end, start)

        if match.groups()[0] is not None: # comment
            yield HtmlDataFragment(start, end)
        elif match.groups()[1] is not None: # <script>...</script>
            for e in _parse_script(match):
                yield e
        else: # tag
            yield _parse_tag(match)
        prev_end = end
    textlen = len(text)
    if prev_end < textlen:
        yield HtmlDataFragment(prev_end, textlen)

def _parse_script(match):
    """parse a <script>...</script> region matched by _HTML_REGEXP"""
    open_text, content, close_text = match.groups()[1:4]

    open_tag = _parse_tag(_HTML_REGEXP.match(open_text))
    open_tag.start = match.start()
    open_tag.end = match.start() + len(open_text)

    close_tag = _parse_tag(_HTML_REGEXP.match(close_text))
    close_tag.start = match.end() - len(close_text)
    close_tag.end = match.end()
    
    yield open_tag
    if open_tag.end < close_tag.start:
        start_pos = 0
        for m in _COMMENT_REGEXP.finditer(content):
            if m.start() > start_pos:
                yield HtmlDataFragment(open_tag.end + start_pos, open_tag.end + m.start())
            yield HtmlDataFragment(open_tag.end + m.start(), open_tag.end + m.end())
            start_pos = m.end()
        if open_tag.end + start_pos < close_tag.start:
            yield HtmlDataFragment(open_tag.end + start_pos, close_tag.start)
    yield close_tag

def _parse_tag(match):
    """
    parse a tag matched by _HTML_REGEXP
    """
    data = match.groups()
    closing, tag, attr_text = data[4:7]
    # if tag is None then the match is a comment
    if tag is not None:
        unpaired = data[-1]
        if closing:
            tag_type = HtmlTagType.CLOSE_TAG
        elif unpaired:
            tag_type = HtmlTagType.UNPAIRED_TAG
        else:
            tag_type = HtmlTagType.OPEN_TAG
        attributes = []
        for attr_match in _ATTR_REGEXP.findall(attr_text):
            name = attr_match[0].lower()
            values = [v for v in attr_match[1:] if v]
            attributes.append((name, values[0] if values else None))
        return HtmlTag(tag_type, tag.lower(), dict(attributes), match.start(), match.end())

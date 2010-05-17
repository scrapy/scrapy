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

_ATTR = "((?:[^=/>\s]|/(?!>))+)(?:\s*=(?:\s*\"(.*?)\"|\s*'(.*?)'|([^>\s]+))?)?"
_TAG = "<(\/?)(\w+(?::\w+)?)((?:\s+" + _ATTR + ")+\s*|\s*)(\/?)>"
_DOCTYPE = r"<!DOCTYPE.*?>"

_ATTR_REGEXP = re.compile(_ATTR, re.I | re.DOTALL)
_HTML_REGEXP = re.compile(_TAG, re.I | re.DOTALL)
_DOCTYPE_REGEXP = re.compile("(?:%s)" % _DOCTYPE)
_COMMENT_RE = re.compile("(<!--.*?-->)", re.DOTALL)
_SCRIPT_RE = re.compile("(<script.*?>).*?(</script.*?>)", re.DOTALL | re.I)

def parse_html(text):
    """Higher level html parser. Calls lower level parsers and joins sucesive
    HtmlDataFragment elements in a single one.
    """
    script_layer = lambda x: _parse_clean_html(x, _SCRIPT_RE, HtmlTag, _simple_parse_html)
    comment_layer = lambda x: _parse_clean_html(x, _COMMENT_RE, HtmlDataFragment, script_layer)
    delayed_element = None
    for element in comment_layer(text):
        if isinstance(element, HtmlTag):
            if delayed_element is not None:
                yield delayed_element
                delayed_element = None
            yield element
        else:# element is HtmlDataFragment
            if delayed_element is not None:
                delayed_element.start = min(element.start, delayed_element.start)
                delayed_element.end = max(element.end, delayed_element.end)
            else:
                delayed_element = element
    if delayed_element is not None:
        yield delayed_element

def _parse_clean_html(text, regex, htype, func):
    """
    Removes regions from text, passes the cleaned text to the lower parse layer,
    and reinserts removed regions.
    regex - regular expression that defines regions to be removed/re inserted
    htype - the html parser type of the removed elements
    func - function that performs the lower parse layer
    """
    removed = [[m.start(), m.end(), m.groups()] for m in regex.finditer(text)]
    
    cleaned = regex.sub("", text)
    shift = 0
    for element in func(cleaned):
        element.start += shift
        element.end += shift
        while removed:
            if element.end <= removed[0][0]:
                yield element
                break
            else:
                start, end, groups = removed.pop(0)
                add = end - start
                element.end += add
                shift += add
                if element.start >= start:
                    element.start += add
                elif isinstance(element, HtmlTag):
                    yield element
                    break
                
                if element.start < start:
                    yield HtmlDataFragment(element.start, start)
                    element.start = end
                
                if htype == HtmlTag:
                    begintag = _parse_tag(_HTML_REGEXP.match(groups[0]))
                    endtag = _parse_tag(_HTML_REGEXP.match(groups[1]))
                    begintag.start = start
                    begintag.end += start
                    
                    endtag.start = end - endtag.end
                    endtag.end = end
                    content = None
                    if begintag.end < endtag.start:
                        content = HtmlDataFragment(begintag.end, endtag.start)
                    yield begintag
                    if content is not None:
                        yield content
                    yield endtag
                else:
                    yield htype(start, end)
        else:
            yield element

def _simple_parse_html(text):
    """Simple html parse. It returns a sequence of HtmlTag and HtmlDataFragment
    objects. Does not ignore any region.
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
        
        yield _parse_tag(match)
        prev_end = end
    textlen = len(text)
    if prev_end < textlen:
        yield HtmlDataFragment(prev_end, textlen)

def _parse_tag(match):
    """
    parse a tag matched by _HTML_REGEXP
    """
    data = match.groups()
    closing, tag, attr_text = data[:3]
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

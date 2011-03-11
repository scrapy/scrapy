"""
Extractors for attributes
"""
import re
import urlparse

from scrapy.utils.markup import remove_entities, remove_comments
from scrapy.utils.url import safe_url_string
from scrapy.contrib.ibl.htmlpage import HtmlTag, HtmlTagType

#FIXME: the use of "." needs to be localized
_NUMERIC_ENTITIES = re.compile("&#([0-9]+)(?:;|\s)", re.U)
_PRICE_NUMBER_RE = re.compile('(?:^|[^a-zA-Z0-9])(\d+(?:\.\d+)?)(?:$|[^a-zA-Z0-9])')
_NUMBER_RE = re.compile('(\d+(?:\.\d+)?)')

_IMAGES = (
    'mng', 'pct', 'bmp', 'gif', 'jpg', 'jpeg', 'png', 'pst', 'psp', 'tif',
    'tiff', 'ai', 'drw', 'dxf', 'eps', 'ps', 'svg',
)

_IMAGES_TYPES = '|'.join(_IMAGES)
_CSS_IMAGERE = re.compile("background(?:-image)?\s*:\s*url\((.*?)\)", re.I)
_BASE_PATH_RE = "/?(?:[^/]+/)*(?:.+%s)"
_IMAGE_PATH_RE = re.compile(_BASE_PATH_RE % '\.(?:%s)' % _IMAGES_TYPES, re.I)
_GENERIC_PATH_RE = re.compile(_BASE_PATH_RE % '', re.I)
_WS = re.compile("\s+", re.U)

# tags to keep (only for attributes with markup)
_TAGS_TO_KEEP = frozenset(['br', 'p', 'big', 'em', 'small', 'strong', 'sub', 
    'sup', 'ins', 'del', 'code', 'kbd', 'samp', 'tt', 'var', 'pre', 'listing',
    'plaintext', 'abbr', 'acronym', 'address', 'bdo', 'blockquote', 'q', 
    'cite', 'dfn', 'table', 'tr', 'th', 'td', 'tbody', 'ul', 'ol', 'li', 'dl',
    'dd', 'dt'])

# tag names to be replaced by other tag names (overrides tags_to_keep)
_TAGS_TO_REPLACE = {
    'h1': 'strong',
    'h2': 'strong',
    'h3': 'strong',
    'h4': 'strong',
    'h5': 'strong',
    'h6': 'strong',
    'b' : 'strong',
    'i' : 'em',
}

# tags whoose content will be completely removed (recursively)
# (overrides tags_to_keep and tags_to_replace)
_TAGS_TO_PURGE = ('script', 'img', 'input')

def htmlregion(text):
    """convenience function to make an html region from text.
    This is useful for testing
    """
    from scrapy.contrib.ibl.htmlpage import HtmlPage
    return HtmlPage(body=text).subregion()

def notags(region, tag_replace=u' '):
    """Removes all html tags"""
    fragments = getattr(region, 'parsed_fragments', None)
    if fragments is None:
        return region
    page = region.htmlpage
    data = [page.fragment_data(f) for f in fragments if not isinstance(f, HtmlTag)]
    return tag_replace.join(data)

def text(region):
    """Converts HTML to text. There is no attempt at formatting other than
    removing excessive whitespace,
    
    For example:
    >>> t = lambda s: text(htmlregion(s))
    >>> t(u'<h1>test</h1>')
    u'test'
    
    Leading and trailing whitespace are removed
    >>> t(u'<h1> test</h1> ')
    u'test'
    
    Comments are removed
    >>> t(u'test <!-- this is a comment --> me')
    u'test me'
    
    Text between script tags is ignored
    >>> t(u"scripts are<script>n't</script> ignored")
    u'scripts are ignored'
    
    HTML entities are converted to text
    >>> t(u"only &pound;42")
    u'only \\xa342'
    """
    chunks = _process_markup(region, 
        lambda text: remove_entities(text, encoding=region.htmlpage.encoding),
        lambda tag: u' '
    )
    text = u''.join(chunks)
    return _WS.sub(u' ', text).strip()

def safehtml(region, allowed_tags=_TAGS_TO_KEEP, replace_tags=_TAGS_TO_REPLACE):
    """Creates an HTML subset, using a whitelist of HTML tags.

    The HTML generated is safe for display on a website,without escaping and
    should not cause formatting problems.
    
    Allowed_tags is a set of tags that are allowed and replace_tags is a mapping of 
    tags to alternative tags to substitute.

    For example:
    >>> t = lambda s: safehtml(htmlregion(s))
    >>> t(u'<strong>test <blink>test</blink></strong>')
    u'<strong>test test</strong>'
    
    Some tags, like script, are completely removed
    >>> t(u'<script>test </script>test')
    u'test'

    replace_tags define tags that are converted. By default all headers, bold and indenting
    are converted to strong and em.
    >>> t(u'<h2>header</h2> test <b>bold</b> <i>indent</i>')
    u'<strong>header</strong> test <strong>bold</strong> <em>indent</em>'

    Comments are stripped, but entities are not converted
    >>> t(u'<!-- comment --> only &pound;42')
    u'only &pound;42'
    
    Paired tags are closed
    >>> t(u'<p>test')
    u'<p>test</p>'

    >>> t(u'<p>test <i><br/><b>test</p>')
    u'<p>test <em><br/><strong>test</strong></em></p>'

    """
    tagstack = []
    def _process_tag(tag):
        tagstr = replace_tags.get(tag.tag, tag.tag)
        if tagstr not in allowed_tags:
            return
        if tag.tag_type == HtmlTagType.OPEN_TAG:
            tagstack.append(tagstr)
            return u"<%s>" % tagstr
        elif tag.tag_type == HtmlTagType.CLOSE_TAG:
            try:
                last = tagstack.pop()
                # common case of matching tag
                if last == tagstr:
                    return u"</%s>" % last
                # output all preceeding tags (if present)
                revtags = tagstack[::-1]
                tindex = revtags.index(tagstr)
                del tagstack[-tindex-1:]
                return u"</%s></%s>" % (last, u"></".join(revtags[:tindex+1]))
            except (ValueError, IndexError):
                # popped from empty stack or failed to find the tag
                pass 
        else:
            assert tag.tag_type == HtmlTagType.UNPAIRED_TAG, "unrecognised tag type"
            return u"<%s/>" % tag.tag
    chunks = list(_process_markup(region, lambda text: text, _process_tag)) + \
        ["</%s>" % t for t in reversed(tagstack)]
    return u''.join(chunks).strip()

def _process_markup(region, textf, tagf):
    fragments = getattr(region, 'parsed_fragments', None)
    if fragments is None:
        yield textf(region)
        return
    fiter = iter(fragments)
    for fragment in fiter:
        if isinstance(fragment, HtmlTag):
            # skip forward to closing script tags
            tag = fragment.tag
            if tag in _TAGS_TO_PURGE:
                # if opening, keep going until closed
                if fragment.tag_type == HtmlTagType.OPEN_TAG:
                    for probe in fiter:
                        if isinstance(probe, HtmlTag) and \
                            probe.tag == tag and \
                            probe.tag_type == HtmlTagType.CLOSE_TAG:
                            break
            else:
                output = tagf(fragment)
                if output:
                    yield output
        else:
            text = region.htmlpage.fragment_data(fragment)
            text = remove_comments(text)
            text = textf(text)
            if text:
                yield text

def html(pageregion):
    """A page region is already html, so this is the identity function"""
    return pageregion

def contains_any_numbers(txt):
    """text that must contain at least one number
    >>> contains_any_numbers('foo')
    >>> contains_any_numbers('$67 at 15% discount')
    '$67 at 15% discount'
    """
    if _NUMBER_RE.search(txt) is not None:
        return txt

def contains_prices(txt):
    """text must contain a number that is not joined to text"""
    if _PRICE_NUMBER_RE.findall(txt) is not None:
        return txt

def contains_numbers(txt, count=1):
    """Must contain a certain amount of numbers
    
    >>> contains_numbers('foo', 2)
    >>> contains_numbers('this 1 has 2 numbers', 2)
    'this 1 has 2 numbers'
    """
    numbers = _NUMBER_RE.findall(txt)
    if len(numbers) == count:
        return txt

def extract_number(txt):
    """Extract a numeric value.
    
    This will fail if more than one numeric value is present.

    >>> extract_number('  45.3')
    '45.3'
    >>> extract_number('  45.3, 7')

    It will handle unescaped entities:
    >>> extract_number(u'&#163;129&#46;99')
    u'129.99'
    """
    txt = _NUMERIC_ENTITIES.sub(lambda m: unichr(int(m.groups()[0])), txt)
    numbers = _NUMBER_RE.findall(txt)
    if len(numbers) == 1:
        return numbers[0]
    
def url(txt):
    """convert text to a url
    
    this is quite conservative, since relative urls are supported
    """
    txt = txt.strip("\t\r\n '\"")
    if txt:
        return txt

def image_url(txt):
    """convert text to a url
    
    this is quite conservative, since relative urls are supported
    Example:

        >>> image_url('')

        >>> image_url('   ')

        >>> image_url(' \\n\\n  ')

        >>> image_url('foo-bar.jpg')
        ['foo-bar.jpg']
        >>> image_url('/images/main_logo12.gif')
        ['/images/main_logo12.gif']
        >>> image_url("http://www.image.com/image.jpg")
        ['http://www.image.com/image.jpg']
        >>> image_url("http://www.domain.com/path1/path2/path3/image.jpg")
        ['http://www.domain.com/path1/path2/path3/image.jpg']
        >>> image_url("/path1/path2/path3/image.jpg")
        ['/path1/path2/path3/image.jpg']
        >>> image_url("path1/path2/image.jpg")
        ['path1/path2/image.jpg']
        >>> image_url("background-image : url(http://www.site.com/path1/path2/image.jpg)")
        ['http://www.site.com/path1/path2/image.jpg']
        >>> image_url("background-image : url('http://www.site.com/path1/path2/image.jpg')")
        ['http://www.site.com/path1/path2/image.jpg']
        >>> image_url('background-image : url("http://www.site.com/path1/path2/image.jpg")')
        ['http://www.site.com/path1/path2/image.jpg']
        >>> image_url("background : url(http://www.site.com/path1/path2/image.jpg)")
        ['http://www.site.com/path1/path2/image.jpg']
        >>> image_url("background : url('http://www.site.com/path1/path2/image.jpg')")
        ['http://www.site.com/path1/path2/image.jpg']
        >>> image_url('background : url("http://www.site.com/path1/path2/image.jpg")')
        ['http://www.site.com/path1/path2/image.jpg']
        >>> image_url('/getimage.php?image=totalgardens/outbbq2_400.jpg&type=prod&resizeto=350')
        ['/getimage.php?image=totalgardens/outbbq2_400.jpg&type=prod&resizeto=350']
        >>> image_url('http://www.site.com/getimage.php?image=totalgardens/outbbq2_400.jpg&type=prod&resizeto=350')
        ['http://www.site.com/getimage.php?image=totalgardens/outbbq2_400.jpg&type=prod&resizeto=350']
        >>> image_url('http://s7d4.scene7.com/is/image/Kohler/jaa03267?hei=425&wid=457&op_usm=2,1,2,1&qlt=80')
        ['http://s7d4.scene7.com/is/image/Kohler/jaa03267?hei=425&wid=457&op_usm=2,1,2,1&qlt=80']
        >>> image_url('../image.aspx?thumb=true&amp;boxSize=175&amp;img=Unknoportrait[1].jpg')
        ['../image.aspx?thumb=true&boxSize=175&img=Unknoportrait%5B1%5D.jpg']
        >>> image_url('http://www.sundancecatalog.com/mgen/catalog/test.ms?args=%2245932|MERIDIAN+PENDANT|.jpg%22&is=336,336,0xffffff')
        ['http://www.sundancecatalog.com/mgen/catalog/test.ms?args=%2245932|MERIDIAN+PENDANT|.jpg%22&is=336,336,0xffffff']
        >>> image_url('http://www.site.com/image.php')
        ['http://www.site.com/image.php']
        >>> image_url('background-image:URL(http://s7d5.scene7.com/is/image/wasserstrom/165133?wid=227&hei=227&amp;defaultImage=noimage_wasserstrom)')
        ['http://s7d5.scene7.com/is/image/wasserstrom/165133?wid=227&hei=227&defaultImage=noimage_wasserstrom']

    """
    imgurl = extract_image_url(txt)
    return [safe_url_string(remove_entities(url(imgurl)))] if imgurl else None

def extract_image_url(txt):
    txt = url(txt)
    imgurl = None
    if txt:
        # check if the text is style content
        m = _CSS_IMAGERE.search(txt)
        txt = m.groups()[0] if m else txt
        parsed = urlparse.urlparse(txt)
        path = None
        m = _IMAGE_PATH_RE.search(parsed.path)
        if m:
            path = m.group()
        elif parsed.query:
            m = _GENERIC_PATH_RE.search(parsed.path)
            if m:
                path = m.group()
        if path is not None:
            parsed = list(parsed)
            parsed[2] = path
            imgurl = urlparse.urlunparse(parsed)
        if not imgurl:
            imgurl = txt
    return imgurl

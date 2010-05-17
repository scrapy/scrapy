"""
Extractors for attributes
"""
import re
import urlparse

from scrapy.utils.markup import remove_entities
from scrapy.utils.url import safe_url_string

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

def text(txt):
    stripped = txt.strip() if txt else None
    if stripped:
        return stripped

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
    return [safe_url_string(remove_entities(url(imgurl)))] if imgurl else None

"""
Link extractor based on lxml.html
"""
import six
from six.moves.urllib.parse import urljoin

import lxml.etree as etree
from w3lib.html import strip_html5_whitespace
from w3lib.url import canonicalize_url

from scrapy.link import Link
from scrapy.utils.misc import arg_to_iter, rel_has_nofollow
from scrapy.utils.python import unique as unique_list, to_native_str
from scrapy.utils.response import get_base_url
from scrapy.linkextractors import FilteringLinkExtractor


# from lxml/src/lxml/html/__init__.py
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"

_collect_string_content = etree.XPath("string()")


def _nons(tag):
    if isinstance(tag, six.string_types):
        if tag[0] == '{' and tag[1:len(XHTML_NAMESPACE)+1] == XHTML_NAMESPACE:
            return tag.split('}')[-1]
    return tag


class LxmlParserLinkExtractor(object):
    def __init__(self, tag="a", attr="href", process=None, unique=False,
                 strip=True, canonicalized=False):
        self.scan_tag = tag if callable(tag) else lambda t: t == tag
        self.scan_attr = attr if callable(attr) else lambda a: a == attr
        self.process_attr = process if callable(process) else lambda v: v
        self.unique = unique
        self.strip = strip
        if canonicalized:
            self.link_key = lambda link: link.url
        else:
            self.link_key = lambda link: canonicalize_url(link.url,
                                                          keep_fragments=True)

    def _iter_links(self, document):
        for el in document.iter(etree.Element):
            if not self.scan_tag(_nons(el.tag)):
                continue
            attribs = el.attrib
            for attrib in attribs:
                if not self.scan_attr(attrib):
                    continue
                yield (el, attrib, attribs[attrib])

    def _extract_links(self, selector, response_url, response_encoding, base_url):
        links = []
        # hacky way to get the underlying lxml parsed document
        for el, attr, attr_val in self._iter_links(selector.root):
            # pseudo lxml.html.HtmlElement.make_links_absolute(base_url)
            try:
                if self.strip:
                    attr_val = strip_html5_whitespace(attr_val)
                attr_val = urljoin(base_url, attr_val)
            except ValueError:
                continue  # skipping bogus links
            else:
                url = self.process_attr(attr_val)
                if url is None:
                    continue
            url = to_native_str(url, encoding=response_encoding)
            # to fix relative links after process_value
            url = urljoin(response_url, url)
            link = Link(url, _collect_string_content(el) or u'',
                        nofollow=rel_has_nofollow(el.get('rel')))
            links.append(link)
        return self._deduplicate_if_needed(links)

    def extract_links(self, response):
        base_url = get_base_url(response)
        return self._extract_links(response.selector, response.url, response.encoding, base_url)

    def _process_links(self, links):
        """ Normalize and filter extracted links

        The subclass should override it if neccessary
        """
        return self._deduplicate_if_needed(links)

    def _deduplicate_if_needed(self, links):
        if self.unique:
            return unique_list(links, key=self.link_key)
        return links


class LxmlLinkExtractor(FilteringLinkExtractor):
    """LxmlLinkExtractor is the recommended link extractor with handy filtering
    options. It is implemented using lxml's robust HTMLParser.

    :param allow: a single regular expression (or list of regular expressions)
        that the (absolute) urls must match in order to be extracted. If not
        given (or empty), it will match all links.

    :param deny: a single regular expression (or list of regular expressions)
        that the (absolute) urls must match in order to be excluded (ie. not
        extracted). It has precedence over the ``allow`` parameter. If not
        given (or empty) it won't exclude any links.

    :param allow_domains: a single value or a list of string containing
        domains which will be considered for extracting the links
    :type allow_domains: str or list

    :param deny_domains: a single value or a list of strings containing
        domains which won't be considered for extracting the links
    :type deny_domains: str or list

    :param deny_extensions: a single value or list of strings containing
        extensions that should be ignored when extracting links.
        If not given, it will default to
        :data:`~scrapy.linkextractors.IGNORED_EXTENSIONS`.
    :type deny_extensions: list

    :param restrict_xpaths: is an XPath (or list of XPath's) which defines
        regions inside the response where links should be extracted from.
        If given, only the text selected by those XPath will be scanned for
        links. See examples below.
    :type restrict_xpaths: str or list

    :param restrict_css: a CSS selector (or list of selectors) which defines
        regions inside the response where links should be extracted from.
        Has the same behaviour as ``restrict_xpaths``.
    :type restrict_css: str or list

    :param tags: a tag or a list of tags to consider when extracting links.
        Defaults to ``('a', 'area')``.
    :type tags: str or list

    :param attrs: an attribute or list of attributes which should be considered when looking
        for links to extract (only for those tags specified in the ``tags``
        parameter). Defaults to ``('href',)``
    :type attrs: list

    :param canonicalize: canonicalize each extracted url (using
        w3lib.url.canonicalize_url). Defaults to ``False``.
        Note that canonicalize_url is meant for duplicate checking;
        it can change the URL visible at server side, so the response can be
        different for requests with canonicalized and raw URLs. If you're
        using LinkExtractor to follow links it is more robust to
        keep the default ``canonicalize=False``.
    :type canonicalize: bool

    :param unique: whether duplicate filtering should be applied to extracted
        links.
    :type unique: bool

    :param process_value: a function which receives each value extracted from
        the tag and attributes scanned and can modify the value and return a
        new one, or return ``None`` to ignore the link altogether. If not
        given, ``process_value`` defaults to ``lambda x: x``.

        For example, to extract links from this code:

        .. code-block:: html

            <a href="javascript:goToPage('../other/page.html'); return false">Link text</a>

        You can use the following function in ``process_value``::

            def process_value(value):
                m = re.search("javascript:goToPage\('(.*?)'", value)
                if m:
                    return m.group(1)

    :param strip: whether to strip whitespaces from extracted attributes.
        According to HTML5 standard, leading and trailing whitespaces
        must be stripped from ``href`` attributes of ``<a>``, ``<area>``
        and many other elements, ``src`` attribute of ``<img>``, ``<iframe>``
        elements, etc., so LinkExtractor strips space chars by default.
        Set ``strip=False`` to turn it off (e.g. if you're extracting urls
        from elements or attributes which allow leading/trailing whitespaces).
    :type strip: bool
    """

    def __init__(self, allow=(), deny=(), allow_domains=(), deny_domains=(), restrict_xpaths=(),
                 tags=('a', 'area'), attrs=('href',), canonicalize=False,
                 unique=True, process_value=None, deny_extensions=None, restrict_css=(),
                 strip=True):
        tags, attrs = set(arg_to_iter(tags)), set(arg_to_iter(attrs))
        tag_func = lambda x: x in tags
        attr_func = lambda x: x in attrs
        lx = LxmlParserLinkExtractor(
            tag=tag_func,
            attr=attr_func,
            unique=unique,
            process=process_value,
            strip=strip,
            canonicalized=canonicalize
        )

        super(LxmlLinkExtractor, self).__init__(lx, allow=allow, deny=deny,
            allow_domains=allow_domains, deny_domains=deny_domains,
            restrict_xpaths=restrict_xpaths, restrict_css=restrict_css,
            canonicalize=canonicalize, deny_extensions=deny_extensions)

    def extract_links(self, response):
        base_url = get_base_url(response)
        if self.restrict_xpaths:
            docs = [subdoc
                    for x in self.restrict_xpaths
                    for subdoc in response.xpath(x)]
        else:
            docs = [response.selector]
        all_links = []
        for doc in docs:
            links = self._extract_links(doc, response.url, response.encoding, base_url)
            all_links.extend(self._process_links(links))
        return unique_list(all_links)

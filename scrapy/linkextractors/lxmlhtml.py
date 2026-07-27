"""
Link extractor based on lxml.html
"""

from __future__ import annotations

import logging
import operator
import re
from collections.abc import Callable, Iterable
from functools import partial
from typing import TYPE_CHECKING, Any, TypeAlias, cast
from urllib.parse import urljoin, urlparse

from lxml import etree
from parsel.csstranslator import HTMLTranslator
from w3lib.html import strip_html5_whitespace
from w3lib.url import canonicalize_url, safe_url_string

from scrapy.link import Link
from scrapy.linkextractors import IGNORED_EXTENSIONS, _is_valid_url, _matches
from scrapy.utils.misc import arg_to_iter, rel_has_nofollow
from scrapy.utils.python import unique as unique_list
from scrapy.utils.url import url_has_any_extension, url_is_from_any_domain

if TYPE_CHECKING:
    from lxml.html import HtmlElement

    from scrapy import Selector
    from scrapy.http import TextResponse


logger = logging.getLogger(__name__)

# from lxml/src/lxml/html/__init__.py
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"

_collect_string_content = etree.XPath("string()")


def _nons(tag: Any) -> Any:
    if (
        isinstance(tag, str)
        and tag[0] == "{"
        and tag[1 : len(XHTML_NAMESPACE) + 1] == XHTML_NAMESPACE
    ):
        return tag.split("}")[-1]
    return tag


def _identity(x: Any) -> Any:
    return x


def _canonicalize_link_url(link: Link) -> str:
    return canonicalize_url(link.url, keep_fragments=True)


def _name_matches(allowed: set[str], denied: set[str], name: str) -> bool:
    """Return whether a tag or attribute *name* should be considered.

    A name matches when it is allowed and not denied. A name is allowed if it is
    listed in *allowed*, or if *allowed* contains the ``"*"`` wildcard, which
    matches every name. *denied* has precedence over *allowed*.
    """
    if name in denied:
        return False
    return "*" in allowed or name in allowed


class LxmlParserLinkExtractor:
    def __init__(
        self,
        tag: str | Callable[[str], bool] = "a",
        attr: str | Callable[[str], bool] = "href",
        process: Callable[[Any], Any] | None = None,
        unique: bool = False,
        strip: bool = True,
        canonicalized: bool = False,
    ):
        # mypy doesn't infer types for operator.* and also for partial()
        self.scan_tag: Callable[[str], bool] = (
            tag
            if callable(tag)
            else cast("Callable[[str], bool]", partial(operator.eq, tag))
        )
        self.scan_attr: Callable[[str], bool] = (
            attr
            if callable(attr)
            else cast("Callable[[str], bool]", partial(operator.eq, attr))
        )
        self.process_attr: Callable[[Any], Any] = (
            process if callable(process) else _identity
        )
        self.unique: bool = unique
        self.strip: bool = strip
        self.link_key: Callable[[Link], str] = (
            cast("Callable[[Link], str]", operator.attrgetter("url"))
            if canonicalized
            else _canonicalize_link_url
        )

    def _iter_links(
        self, document: HtmlElement
    ) -> Iterable[tuple[HtmlElement, str, str]]:
        for el in document.iter(etree.Element):
            if not self.scan_tag(_nons(el.tag)):
                continue
            attribs = el.attrib
            for attrib in attribs:
                if not self.scan_attr(attrib):
                    continue
                yield el, attrib, attribs[attrib]

    def _extract_links(
        self,
        selector: Selector,
        response_url: str,
        response_encoding: str,
        base_url: str,
    ) -> list[Link]:
        links: list[Link] = []
        # hacky way to get the underlying lxml parsed document
        for el, _, attr_val in self._iter_links(selector.root):
            # pseudo lxml.html.HtmlElement.make_links_absolute(base_url)
            try:
                if self.strip:
                    attr_val = strip_html5_whitespace(attr_val)  # noqa: PLW2901 this is intended
                attr_val = urljoin(base_url, attr_val)  # noqa: PLW2901
            except ValueError:
                continue  # skipping bogus links
            else:
                url = self.process_attr(attr_val)
                if url is None:
                    continue
            try:
                url = safe_url_string(url, encoding=response_encoding)
            except ValueError:
                logger.debug(f"Skipping extraction of link with bad URL {url!r}")
                continue

            # to fix relative links after process_value
            url = urljoin(response_url, url)
            link = Link(
                url,
                _collect_string_content(el) or "",
                nofollow=rel_has_nofollow(el.get("rel")),
            )
            links.append(link)
        return self._deduplicate_if_needed(links)

    def extract_links(self, response: TextResponse) -> list[Link]:
        return self._extract_links(
            response.selector,
            response.url,
            response.encoding,
            response.base_url,
        )

    def _process_links(self, links: list[Link]) -> list[Link]:
        """Normalize and filter extracted links

        The subclass should override it if necessary
        """
        return self._deduplicate_if_needed(links)

    def _deduplicate_if_needed(self, links: list[Link]) -> list[Link]:
        if self.unique:
            return unique_list(links, key=self.link_key)
        return links


_Regex: TypeAlias = str | re.Pattern[str]
_RegexOrSeveral: TypeAlias = _Regex | Iterable[_Regex]


class LxmlLinkExtractor:
    r"""LxmlLinkExtractor is the recommended link extractor with handy filtering
    options. It is implemented using lxml's robust HTMLParser.

    :param allow: a single regular expression (or list of regular expressions)
        that the (absolute) urls must match in order to be extracted. If not
        given (or empty), it will match all links.
    :type allow: str or list

    :param deny: a single regular expression (or list of regular expressions)
        that the (absolute) urls must match in order to be excluded (i.e. not
        extracted). It has precedence over the ``allow`` parameter. If not
        given (or empty) it won't exclude any links.
    :type deny: str or list

    :param allow_domains: a single value or a list of string containing
        domains which will be considered for extracting the links
    :type allow_domains: str or list

    :param deny_domains: a single value or a list of strings containing
        domains which won't be considered for extracting the links
    :type deny_domains: str or list

    :param deny_extensions: a single value or list of strings containing
        extensions that should be ignored when extracting links.
        If not given, it will default to
        :data:`scrapy.linkextractors.IGNORED_EXTENSIONS`.
    :type deny_extensions: list

    :param restrict_xpaths: is an XPath (or list of XPath's) which defines
        regions inside the response where links should be extracted from.
        If given, only the text selected by those XPath will be scanned for
        links.
    :type restrict_xpaths: str or list

    :param restrict_css: a CSS selector (or list of selectors) which defines
        regions inside the response where links should be extracted from.
        Has the same behaviour as ``restrict_xpaths``.
    :type restrict_css: str or list

    :param restrict_text: a single regular expression (or list of regular
        expressions) that the link's text must match in order to be extracted.
        If not given (or empty), it will match all links. If a list of regular
        expressions is given, the link will be extracted if it matches at least
        one.
    :type restrict_text: str or list

    :param tags: a tag or a list of tags to consider when extracting links.
        Defaults to ``('a', 'area')``. Use ``'*'`` to consider every tag.
    :type tags: str or list

    :param attrs: an attribute or list of attributes which should be considered
        when looking for links to extract (only for those tags specified in the
        ``tags`` parameter). Defaults to ``('href',)``. Use ``'*'`` to consider
        every attribute.
    :type attrs: list

    :param deny_tags: a tag or a list of tags that should not be considered when
        extracting links. It has precedence over the ``tags`` parameter, so it
        can be combined with ``tags='*'`` to consider every tag except a few.
        Defaults to ``()`` (no tag is excluded).

        .. versionadded:: 2.17.0
    :type deny_tags: str or list

    :param deny_attrs: an attribute or a list of attributes that should not be
        considered when looking for links to extract. It has precedence over the
        ``attrs`` parameter, so it can be combined with ``attrs='*'`` to consider
        every attribute except a few. Defaults to ``()`` (no attribute is
        excluded).

        .. versionadded:: 2.17.0
    :type deny_attrs: str or list

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

        .. highlight:: html

        For example, to extract links from this code::

            <a href="javascript:goToPage('../other/page.html'); return false">Link text</a>

        .. highlight:: python

        You can use the following function in ``process_value``:

        .. code-block:: python

            def process_value(value):
                m = re.search(r"javascript:goToPage\('(.*?)'", value)
                if m:
                    return m.group(1)

    :type process_value: collections.abc.Callable

    :param strip: whether to strip whitespaces from extracted attributes.
        According to HTML5 standard, leading and trailing whitespaces
        must be stripped from ``href`` attributes of ``<a>``, ``<area>``
        and many other elements, ``src`` attribute of ``<img>``, ``<iframe>``
        elements, etc., so LinkExtractor strips space chars by default.
        Set ``strip=False`` to turn it off (e.g. if you're extracting urls
        from elements or attributes which allow leading/trailing whitespaces).
    :type strip: bool
    """

    _csstranslator = HTMLTranslator()

    def __init__(
        self,
        allow: _RegexOrSeveral = (),
        deny: _RegexOrSeveral = (),
        allow_domains: str | Iterable[str] = (),
        deny_domains: str | Iterable[str] = (),
        restrict_xpaths: str | Iterable[str] = (),
        tags: str | Iterable[str] = ("a", "area"),
        attrs: str | Iterable[str] = ("href",),
        canonicalize: bool = False,
        unique: bool = True,
        process_value: Callable[[Any], Any] | None = None,
        deny_extensions: str | Iterable[str] | None = None,
        restrict_css: str | Iterable[str] = (),
        strip: bool = True,
        restrict_text: _RegexOrSeveral | None = None,
        deny_tags: str | Iterable[str] = (),
        deny_attrs: str | Iterable[str] = (),
    ):
        tags, attrs = set(arg_to_iter(tags)), set(arg_to_iter(attrs))
        deny_tags, deny_attrs = (
            set(arg_to_iter(deny_tags)),
            set(arg_to_iter(deny_attrs)),
        )
        self.link_extractor = LxmlParserLinkExtractor(
            tag=partial(_name_matches, tags, deny_tags),
            attr=partial(_name_matches, attrs, deny_attrs),
            unique=unique,
            process=process_value,
            strip=strip,
            canonicalized=not canonicalize,
        )
        self.allow_res: list[re.Pattern[str]] = self._compile_regexes(allow)
        self.deny_res: list[re.Pattern[str]] = self._compile_regexes(deny)

        self.allow_domains: set[str] = set(arg_to_iter(allow_domains))
        self.deny_domains: set[str] = set(arg_to_iter(deny_domains))

        self.restrict_xpaths: tuple[str, ...] = tuple(arg_to_iter(restrict_xpaths))
        self.restrict_xpaths += tuple(
            map(self._csstranslator.css_to_xpath, arg_to_iter(restrict_css))
        )

        if deny_extensions is None:
            deny_extensions = IGNORED_EXTENSIONS
        self.canonicalize: bool = canonicalize
        self.deny_extensions: set[str] = {"." + e for e in arg_to_iter(deny_extensions)}
        self.restrict_text: list[re.Pattern[str]] = self._compile_regexes(restrict_text)

    @staticmethod
    def _compile_regexes(value: _RegexOrSeveral | None) -> list[re.Pattern[str]]:
        return [
            x if isinstance(x, re.Pattern) else re.compile(x)
            for x in arg_to_iter(value)
        ]

    def _link_allowed(self, link: Link) -> bool:
        if not _is_valid_url(link.url):
            return False
        if self.allow_res and not _matches(link.url, self.allow_res):
            return False
        if self.deny_res and _matches(link.url, self.deny_res):
            return False
        parsed_url = urlparse(link.url)
        if self.allow_domains and not url_is_from_any_domain(
            parsed_url, self.allow_domains
        ):
            return False
        if self.deny_domains and url_is_from_any_domain(parsed_url, self.deny_domains):
            return False
        if self.deny_extensions and url_has_any_extension(
            parsed_url, self.deny_extensions
        ):
            return False
        return not self.restrict_text or _matches(link.text, self.restrict_text)

    def matches(self, url: str) -> bool:
        if self.allow_domains and not url_is_from_any_domain(url, self.allow_domains):
            return False
        if self.deny_domains and url_is_from_any_domain(url, self.deny_domains):
            return False

        allowed = (
            (regex.search(url) for regex in self.allow_res)
            if self.allow_res
            else [True]
        )
        denied = (regex.search(url) for regex in self.deny_res) if self.deny_res else ()
        return any(allowed) and not any(denied)

    def _process_links(self, links: list[Link]) -> list[Link]:
        links = [x for x in links if self._link_allowed(x)]
        if self.canonicalize:
            for link in links:
                link.url = canonicalize_url(link.url)
        return self.link_extractor._process_links(links)

    def _extract_links(self, *args: Any, **kwargs: Any) -> list[Link]:
        return self.link_extractor._extract_links(*args, **kwargs)

    def extract_links(self, response: TextResponse) -> list[Link]:
        """Returns a list of :class:`~scrapy.link.Link` objects from the
        specified :class:`response <scrapy.http.Response>`.

        Only links that match the settings passed to the ``__init__`` method of
        the link extractor are returned.

        Duplicate links are omitted if the ``unique`` attribute is set to ``True``,
        otherwise they are returned.
        """
        if self.restrict_xpaths:
            docs = [
                subdoc for x in self.restrict_xpaths for subdoc in response.xpath(x)
            ]
        else:
            docs = [response.selector]
        all_links = []
        for doc in docs:
            links = self._extract_links(
                doc,
                response.url,
                response.encoding,
                response.base_url,
            )
            all_links.extend(self._process_links(links))
        if self.link_extractor.unique:
            return unique_list(all_links, key=self.link_extractor.link_key)
        return all_links

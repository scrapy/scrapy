"""
Link extractor based on lxml.html
"""

from __future__ import annotations

import logging
import operator
import re
from collections.abc import Callable, Iterable
from functools import partial
from typing import TYPE_CHECKING, Any, Union, cast
from urllib.parse import urljoin, urlparse

from lxml import etree  # nosec
from parsel.csstranslator import HTMLTranslator
from w3lib.html import strip_html5_whitespace
from w3lib.url import canonicalize_url, safe_url_string

from scrapy.link import Link
from scrapy.linkextractors import IGNORED_EXTENSIONS, _is_valid_url, _matches
from scrapy.utils.misc import arg_to_iter, rel_has_nofollow
from scrapy.utils.python import unique as unique_list
from scrapy.utils.response import get_base_url
from scrapy.utils.url import url_has_any_extension, url_is_from_any_domain

if TYPE_CHECKING:

    from lxml.html import HtmlElement  # nosec

    from scrapy import Selector
    from scrapy.http import TextResponse


logger = logging.getLogger(__name__)

# from lxml/src/lxml/html/__init__.py
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"

_collect_string_content = etree.XPath("string()")


def _nons(tag: Any) -> Any:
    if isinstance(tag, str):
        if tag[0] == "{" and tag[1 : len(XHTML_NAMESPACE) + 1] == XHTML_NAMESPACE:
            return tag.split("}")[-1]
    return tag


def _identity(x: Any) -> Any:
    return x


def _canonicalize_link_url(link: Link) -> str:
    return canonicalize_url(link.url, keep_fragments=True)


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
            else cast(Callable[[str], bool], partial(operator.eq, tag))
        )
        self.scan_attr: Callable[[str], bool] = (
            attr
            if callable(attr)
            else cast(Callable[[str], bool], partial(operator.eq, attr))
        )
        self.process_attr: Callable[[Any], Any] = (
            process if callable(process) else _identity
        )
        self.unique: bool = unique
        self.strip: bool = strip
        self.link_key: Callable[[Link], str] = (
            cast(Callable[[Link], str], operator.attrgetter("url"))
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
        base_url = get_base_url(response)
        return self._extract_links(
            response.selector, response.url, response.encoding, base_url
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


_RegexT = Union[str, re.Pattern[str]]
_RegexOrSeveralT = Union[_RegexT, Iterable[_RegexT]]


class LxmlLinkExtractor:
    _csstranslator = HTMLTranslator()

    def __init__(
        self,
        allow: _RegexOrSeveralT = (),
        deny: _RegexOrSeveralT = (),
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
        restrict_text: _RegexOrSeveralT | None = None,
    ):
        tags, attrs = set(arg_to_iter(tags)), set(arg_to_iter(attrs))
        self.link_extractor = LxmlParserLinkExtractor(
            tag=partial(operator.contains, tags),
            attr=partial(operator.contains, attrs),
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
    def _compile_regexes(value: _RegexOrSeveralT | None) -> list[re.Pattern[str]]:
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
        if self.restrict_text and not _matches(link.text, self.restrict_text):
            return False
        return True

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
        denied = (regex.search(url) for regex in self.deny_res) if self.deny_res else []
        return any(allowed) and not any(denied)

    def _process_links(self, links: list[Link]) -> list[Link]:
        links = [x for x in links if self._link_allowed(x)]
        if self.canonicalize:
            for link in links:
                link.url = canonicalize_url(link.url)
        links = self.link_extractor._process_links(links)
        return links

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
        base_url = get_base_url(response)
        if self.restrict_xpaths:
            docs = [
                subdoc for x in self.restrict_xpaths for subdoc in response.xpath(x)
            ]
        else:
            docs = [response.selector]
        all_links = []
        for doc in docs:
            links = self._extract_links(doc, response.url, response.encoding, base_url)
            all_links.extend(self._process_links(links))
        if self.link_extractor.unique:
            return unique_list(all_links, key=self.link_extractor.link_key)
        return all_links

from __future__ import annotations

import csv
import logging
import re
from io import StringIO
from typing import TYPE_CHECKING, Any, Literal, cast, overload
from warnings import warn

from lxml import etree

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Response, TextResponse
from scrapy.selector import Selector
from scrapy.utils.python import re_rsearch

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

logger = logging.getLogger(__name__)


def xmliter(obj: Response | str | bytes, nodename: str) -> Iterator[Selector]:
    """Return a iterator of Selector's over all nodes of a XML document,
       given the name of the node to iterate. Useful for parsing XML feeds.

    obj can be:
    - a Response object
    - a unicode string
    - a string encoded as utf-8
    """
    warn(
        (
            "xmliter is deprecated and its use strongly discouraged because "
            "it is vulnerable to ReDoS attacks. Use xmliter_lxml instead. See "
            "https://github.com/scrapy/scrapy/security/advisories/GHSA-cc65-xxvf-f7r9"
        ),
        ScrapyDeprecationWarning,
        stacklevel=2,
    )

    nodename_patt = re.escape(nodename)

    DOCUMENT_HEADER_RE = re.compile(r"<\?xml[^>]+>\s*", re.DOTALL)
    HEADER_END_RE = re.compile(rf"<\s*/{nodename_patt}\s*>", re.DOTALL)
    END_TAG_RE = re.compile(r"<\s*/([^\s>]+)\s*>", re.DOTALL)
    NAMESPACE_RE = re.compile(r"((xmlns[:A-Za-z]*)=[^>\s]+)", re.DOTALL)
    text = _body_or_str(obj)

    document_header_match = re.search(DOCUMENT_HEADER_RE, text)
    document_header = (
        document_header_match.group().strip() if document_header_match else ""
    )
    header_end_idx = re_rsearch(HEADER_END_RE, text)
    header_end = text[header_end_idx[1] :].strip() if header_end_idx else ""
    namespaces: dict[str, str] = {}
    if header_end:
        for tagname in reversed(re.findall(END_TAG_RE, header_end)):
            assert header_end_idx
            tag = re.search(
                rf"<\s*{tagname}.*?xmlns[:=][^>]*>",
                text[: header_end_idx[1]],
                re.DOTALL,
            )
            if tag:
                for x in re.findall(NAMESPACE_RE, tag.group()):
                    namespaces[x[1]] = x[0]

    r = re.compile(rf"<{nodename_patt}[\s>].*?</{nodename_patt}>", re.DOTALL)
    for match in r.finditer(text):
        nodetext = (
            document_header
            + match.group().replace(
                nodename, f"{nodename} {' '.join(namespaces.values())}", 1
            )
            + header_end
        )
        yield Selector(text=nodetext, type="xml")


def xmliter_lxml(
    obj: Response | str | bytes,
    nodename: str,
    namespace: str | None = None,
    prefix: str = "x",
) -> Iterator[Selector]:
    reader = _StreamReader(obj)
    tag = f"{{{namespace}}}{nodename}" if namespace else nodename
    iterable = etree.iterparse(
        reader,
        encoding=reader.encoding,
        events=("end", "start-ns"),
        resolve_entities=False,
        huge_tree=True,
    )
    selxpath = "//" + (f"{prefix}:{nodename}" if namespace else nodename)
    needs_namespace_resolution = not namespace and ":" in nodename
    if needs_namespace_resolution:
        prefix, nodename = nodename.split(":", maxsplit=1)
    for event, data in iterable:
        if event == "start-ns":
            assert isinstance(data, tuple)
            if needs_namespace_resolution:
                _prefix, _namespace = data
                if _prefix != prefix:
                    continue
                namespace = _namespace
                needs_namespace_resolution = False
                selxpath = f"//{prefix}:{nodename}"
                tag = f"{{{namespace}}}{nodename}"
            continue
        assert isinstance(data, etree._Element)
        node = data
        if node.tag != tag:
            continue
        nodetext = etree.tostring(node, encoding="unicode")
        node.clear()
        xs = Selector(text=nodetext, type="xml")
        if namespace:
            xs.register_namespace(prefix, namespace)
        yield xs.xpath(selxpath)[0]


class _StreamReader:
    def __init__(self, obj: Response | str | bytes):
        self._ptr: int = 0
        self._text: str | bytes
        if isinstance(obj, TextResponse):
            self._text, self.encoding = obj.body, obj.encoding
        elif isinstance(obj, Response):
            self._text, self.encoding = obj.body, "utf-8"
        else:
            self._text, self.encoding = obj, "utf-8"
        self._is_unicode: bool = isinstance(self._text, str)
        self._is_first_read: bool = True

    def read(self, n: int = 65535) -> bytes:
        method: Callable[[int], bytes] = (
            self._read_unicode if self._is_unicode else self._read_string
        )
        result = method(n)
        if self._is_first_read:
            self._is_first_read = False
            result = result.lstrip()
        return result

    def _read_string(self, n: int = 65535) -> bytes:
        s, e = self._ptr, self._ptr + n
        self._ptr = e
        return cast(bytes, self._text)[s:e]

    def _read_unicode(self, n: int = 65535) -> bytes:
        s, e = self._ptr, self._ptr + n
        self._ptr = e
        return cast(str, self._text)[s:e].encode("utf-8")


def csviter(
    obj: Response | str | bytes,
    delimiter: str | None = None,
    headers: list[str] | None = None,
    encoding: str | None = None,
    quotechar: str | None = None,
) -> Iterator[dict[str, str]]:
    """Returns an iterator of dictionaries from the given csv object

    obj can be:
    - a Response object
    - a unicode string
    - a string encoded as utf-8

    delimiter is the character used to separate fields on the given obj.

    headers is an iterable that when provided offers the keys
    for the returned dictionaries, if not the first row is used.

    quotechar is the character used to enclosure fields on the given obj.
    """

    if encoding is not None:
        warn(
            "The encoding argument of csviter() is ignored and will be removed"
            " in a future Scrapy version.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )

    lines = StringIO(_body_or_str(obj, unicode=True))

    kwargs: dict[str, Any] = {}
    if delimiter:
        kwargs["delimiter"] = delimiter
    if quotechar:
        kwargs["quotechar"] = quotechar
    csv_r = csv.reader(lines, **kwargs)

    if not headers:
        try:
            headers = next(csv_r)
        except StopIteration:
            return

    for row in csv_r:
        if len(row) != len(headers):
            logger.warning(
                "ignoring row %(csvlnum)d (length: %(csvrow)d, "
                "should be: %(csvheader)d)",
                {
                    "csvlnum": csv_r.line_num,
                    "csvrow": len(row),
                    "csvheader": len(headers),
                },
            )
            continue
        yield dict(zip(headers, row))


@overload
def _body_or_str(obj: Response | str | bytes) -> str: ...


@overload
def _body_or_str(obj: Response | str | bytes, unicode: Literal[True]) -> str: ...


@overload
def _body_or_str(obj: Response | str | bytes, unicode: Literal[False]) -> bytes: ...


def _body_or_str(obj: Response | str | bytes, unicode: bool = True) -> str | bytes:
    expected_types = (Response, str, bytes)
    if not isinstance(obj, expected_types):
        expected_types_str = " or ".join(t.__name__ for t in expected_types)
        raise TypeError(
            f"Object {obj!r} must be {expected_types_str}, not {type(obj).__name__}"
        )
    if isinstance(obj, Response):
        if not unicode:
            return obj.body
        if isinstance(obj, TextResponse):
            return obj.text
        return obj.body.decode("utf-8")
    if isinstance(obj, str):
        return obj if unicode else obj.encode("utf-8")
    return obj.decode("utf-8") if unicode else obj

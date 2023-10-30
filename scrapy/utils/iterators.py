import csv
import logging
import re
from io import StringIO
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generator,
    Iterable,
    List,
    Literal,
    Optional,
    Union,
    cast,
    overload,
)

from scrapy.http import Response, TextResponse
from scrapy.selector import Selector
from scrapy.utils.python import re_rsearch, to_unicode

if TYPE_CHECKING:
    from lxml._types import SupportsReadClose

logger = logging.getLogger(__name__)


def xmliter(
    obj: Union[Response, str, bytes], nodename: str
) -> Generator[Selector, Any, None]:
    """Return a iterator of Selector's over all nodes of a XML document,
       given the name of the node to iterate. Useful for parsing XML feeds.

    obj can be:
    - a Response object
    - a unicode string
    - a string encoded as utf-8
    """
    nodename_patt = re.escape(nodename)

    DOCUMENT_HEADER_RE = re.compile(r"<\?xml[^>]+>\s*", re.S)
    HEADER_END_RE = re.compile(rf"<\s*/{nodename_patt}\s*>", re.S)
    END_TAG_RE = re.compile(r"<\s*/([^\s>]+)\s*>", re.S)
    NAMESPACE_RE = re.compile(r"((xmlns[:A-Za-z]*)=[^>\s]+)", re.S)
    text = _body_or_str(obj)

    document_header_match = re.search(DOCUMENT_HEADER_RE, text)
    document_header = (
        document_header_match.group().strip() if document_header_match else ""
    )
    header_end_idx = re_rsearch(HEADER_END_RE, text)
    header_end = text[header_end_idx[1] :].strip() if header_end_idx else ""
    namespaces: Dict[str, str] = {}
    if header_end:
        for tagname in reversed(re.findall(END_TAG_RE, header_end)):
            assert header_end_idx
            tag = re.search(
                rf"<\s*{tagname}.*?xmlns[:=][^>]*>", text[: header_end_idx[1]], re.S
            )
            if tag:
                for x in re.findall(NAMESPACE_RE, tag.group()):
                    namespaces[x[1]] = x[0]

    r = re.compile(rf"<{nodename_patt}[\s>].*?</{nodename_patt}>", re.DOTALL)
    for match in r.finditer(text):
        nodetext = (
            document_header
            + match.group().replace(
                nodename, f'{nodename} {" ".join(namespaces.values())}', 1
            )
            + header_end
        )
        yield Selector(text=nodetext, type="xml")


def xmliter_lxml(
    obj: Union[Response, str, bytes],
    nodename: str,
    namespace: Optional[str] = None,
    prefix: str = "x",
) -> Generator[Selector, Any, None]:
    from lxml import etree

    reader = _StreamReader(obj)
    tag = f"{{{namespace}}}{nodename}" if namespace else nodename
    iterable = etree.iterparse(
        cast("SupportsReadClose[bytes]", reader), tag=tag, encoding=reader.encoding
    )
    selxpath = "//" + (f"{prefix}:{nodename}" if namespace else nodename)
    for _, node in iterable:
        nodetext = etree.tostring(node, encoding="unicode")
        node.clear()
        xs = Selector(text=nodetext, type="xml")
        if namespace:
            xs.register_namespace(prefix, namespace)
        yield xs.xpath(selxpath)[0]


class _StreamReader:
    def __init__(self, obj: Union[Response, str, bytes]):
        self._ptr: int = 0
        self._text: Union[str, bytes]
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
    obj: Union[Response, str, bytes],
    delimiter: Optional[str] = None,
    headers: Optional[List[str]] = None,
    encoding: Optional[str] = None,
    quotechar: Optional[str] = None,
) -> Generator[Dict[str, str], Any, None]:
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

    encoding = obj.encoding if isinstance(obj, TextResponse) else encoding or "utf-8"

    def row_to_unicode(row_: Iterable) -> List[str]:
        return [to_unicode(field, encoding) for field in row_]

    lines = StringIO(_body_or_str(obj, unicode=True))

    kwargs: Dict[str, Any] = {}
    if delimiter:
        kwargs["delimiter"] = delimiter
    if quotechar:
        kwargs["quotechar"] = quotechar
    csv_r = csv.reader(lines, **kwargs)

    if not headers:
        try:
            row = next(csv_r)
        except StopIteration:
            return
        headers = row_to_unicode(row)

    for row in csv_r:
        row = row_to_unicode(row)
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
def _body_or_str(obj: Union[Response, str, bytes]) -> str:
    ...


@overload
def _body_or_str(obj: Union[Response, str, bytes], unicode: Literal[True]) -> str:
    ...


@overload
def _body_or_str(obj: Union[Response, str, bytes], unicode: Literal[False]) -> bytes:
    ...


def _body_or_str(
    obj: Union[Response, str, bytes], unicode: bool = True
) -> Union[str, bytes]:
    expected_types = (Response, str, bytes)
    if not isinstance(obj, expected_types):
        expected_types_str = " or ".join(t.__name__ for t in expected_types)
        raise TypeError(
            f"Object {obj!r} must be {expected_types_str}, not {type(obj).__name__}"
        )
    if isinstance(obj, Response):
        if not unicode:
            return cast(bytes, obj.body)
        if isinstance(obj, TextResponse):
            return obj.text
        return cast(bytes, obj.body).decode("utf-8")
    if isinstance(obj, str):
        return obj if unicode else obj.encode("utf-8")
    return obj.decode("utf-8") if unicode else obj

"""
This module implements the XMLFeedSpider which is the recommended spider to use
for scraping from an XML feed.

See documentation in docs/topics/spiders.rst
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.exceptions import NotSupported
from scrapy.http import Response, TextResponse
from scrapy.selector import Selector
from scrapy.spiders import Spider
from scrapy.utils.iterators import csviter, xmliter_lxml
from scrapy.utils.spider import iterate_spider_output

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


class XMLFeedSpider(Spider):
    """Spider for parsing XML feeds by iterating through them by a certain node
    name.

    The iterator can be chosen from: ``iternodes``, ``xml``, and ``html``. It's
    recommended to use the ``iternodes`` iterator for performance reasons, since
    the ``xml`` and ``html`` iterators generate the whole DOM at once in order to
    parse it. However, using ``html`` as the iterator may be useful when parsing
    XML with bad markup.

    To set the iterator and the tag name, you must define the :attr:`iterator`
    and :attr:`itertag` class attributes.

    .. warning:: Unlike in other spiders, a request without a callback is not
       handled by :meth:`Spider.parse <scrapy.Spider.parse>`. Its response is
       parsed as an XML feed, calling :meth:`parse_node` for each matching node.

       That is the way to have an additional feed parsed as such. If you want
       your own parsing code to run for it instead, set its callback explicitly;
       defining :meth:`~scrapy.Spider.parse` is not enough.
    """

    #: The iterator to use. It can be either:
    #:
    #: -   ``'iternodes'`` - a fast iterator based on ``lxml``
    #:
    #: -   ``'html'`` - an iterator which uses :class:`~scrapy.Selector`.
    #:     Keep in mind this uses DOM parsing and must load all DOM in memory
    #:     which could be a problem for big feeds. It also parses the feed
    #:     with an HTML parser, which can silently mangle tags that HTML
    #:     treats as void elements, such as ``<link>``, dropping their
    #:     content and closing tag. Use ``xml`` or ``iternodes`` instead
    #:     for feeds affected by this.
    #:
    #: -   ``'xml'`` - an iterator which uses :class:`~scrapy.Selector`.
    #:     Keep in mind this uses DOM parsing and must load all DOM in memory
    #:     which could be a problem for big feeds
    iterator: str = "iternodes"

    #: Name of the node (or element) to iterate in. Example:
    #:
    #: .. code-block:: python
    #:
    #:     itertag = "product"
    itertag: str = "item"

    #: ``(prefix, uri)`` tuples defining the namespaces available in that
    #: document that will be processed with this spider. The ``prefix`` and
    #: ``uri`` will be used to automatically register namespaces using the
    #: :meth:`~scrapy.Selector.register_namespace` method.
    #:
    #: You can then specify nodes with namespaces in the :attr:`itertag`
    #: attribute.
    #:
    #: Example:
    #:
    #: .. code-block:: python
    #:
    #:     from scrapy.spiders import XMLFeedSpider
    #:
    #:
    #:     class YourSpider(XMLFeedSpider):
    #:
    #:         namespaces = [("n", "http://www.sitemaps.org/schemas/sitemap/0.9")]
    #:         itertag = "n:url"
    #:         # ...
    namespaces: Sequence[tuple[str, str]] = ()

    def process_results(
        self, response: Response, results: Iterable[Any]
    ) -> Iterable[Any]:
        """Handle *results*, the items and requests returned by the spider for
        *response*, and return them, either unmodified or with changes.

        Override it to perform any last-time processing required before
        returning the results to the framework core, for example setting the
        item IDs.
        """
        return results

    def adapt_response(self, response: Response) -> Response:
        """Handle *response* as soon as it arrives from the spider middleware,
        before the spider starts parsing it, and return a response, which can be
        the same one or a different one.

        Override it to make any changes you want to the feed before parsing it,
        e.g. to its body.
        """
        return response

    def parse_node(self, response: Response, selector: Selector) -> Any:
        """Handle a node of *response* matching :attr:`itertag`, for which
        *selector* is a :class:`~scrapy.Selector`.

        This is a :meth:`spider callback <scrapy.Spider.parse>`. Overriding it
        is mandatory. Otherwise, your spider won't work.
        """
        if hasattr(self, "parse_item"):  # backward compatibility
            return self.parse_item(response, selector)
        raise NotImplementedError

    def parse_nodes(self, response: Response, nodes: Iterable[Selector]) -> Any:
        """This method is called for the nodes matching the provided tag name
        (itertag). Receives the response and an iterable of Selectors.
        """

        for selector in nodes:
            ret = iterate_spider_output(self.parse_node(response, selector))
            yield from self.process_results(response, ret)

    def _parse(self, response: Response, **kwargs: Any) -> Any:
        response = self.adapt_response(response)
        nodes: Iterable[Selector]
        if self.iterator == "iternodes":
            nodes = self._iternodes(response)
        elif self.iterator == "xml":
            if not isinstance(response, TextResponse):
                raise ValueError("Response content isn't text")
            selector = Selector(response, type="xml")
            self._register_namespaces(selector)
            nodes = selector.xpath(f"//{self.itertag}")
        elif self.iterator == "html":
            if not isinstance(response, TextResponse):
                raise ValueError("Response content isn't text")
            selector = Selector(response, type="html")
            self._register_namespaces(selector)
            nodes = selector.xpath(f"//{self.itertag}")
        else:
            raise NotSupported("Unsupported node iterator")

        return self.parse_nodes(response, nodes)

    def _iternodes(self, response: Response) -> Iterable[Selector]:
        for node in xmliter_lxml(response, self.itertag):
            self._register_namespaces(node)
            yield node

    def _register_namespaces(self, selector: Selector) -> None:
        for prefix, uri in self.namespaces:
            selector.register_namespace(prefix, uri)


class CSVFeedSpider(Spider):
    """Spider for parsing CSV feeds.

    This spider is very similar to :class:`XMLFeedSpider`, except that it
    iterates over rows, instead of nodes. The method that gets called in each
    iteration is :meth:`parse_row`.

    .. warning:: Unlike in other spiders, a request without a callback is not
       handled by :meth:`Spider.parse <scrapy.Spider.parse>`. Its response is
       parsed as a CSV feed, calling :meth:`parse_row` for each row.

       That is the way to have an additional feed parsed as such. If you want
       your own parsing code to run for it instead, set its callback explicitly;
       defining :meth:`~scrapy.Spider.parse` is not enough.
    """

    #: Separator character for each field in the CSV file.
    #:
    #: ``None`` means using the default delimiter of the :mod:`csv` module,
    #: ``','`` (comma).
    delimiter: str | None = None

    #: Enclosure character for each field in the CSV file.
    #:
    #: ``None`` means using the default quote character of the :mod:`csv`
    #: module, ``'"'`` (quotation mark).
    quotechar: str | None = None

    #: Column names in the CSV file.
    headers: list[str] | None = None

    def process_results(
        self, response: Response, results: Iterable[Any]
    ) -> Iterable[Any]:
        """Same as :meth:`XMLFeedSpider.process_results`."""
        return results

    def adapt_response(self, response: Response) -> Response:
        """Same as :meth:`XMLFeedSpider.adapt_response`."""
        return response

    def parse_row(self, response: Response, row: dict[str, str]) -> Any:
        """Handle *row*, a row of *response* as a dict with a key for each
        provided (or detected) header of the CSV file.

        Overriding this method is mandatory. Otherwise, your spider won't work.
        """
        raise NotImplementedError

    def parse_rows(self, response: Response) -> Any:
        for row in csviter(
            response, self.delimiter, self.headers, quotechar=self.quotechar
        ):
            ret = iterate_spider_output(self.parse_row(response, row))
            yield from self.process_results(response, ret)

    def _parse(self, response: Response, **kwargs: Any) -> Any:
        response = self.adapt_response(response)
        return self.parse_rows(response)

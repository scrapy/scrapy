"""
This module implements the XMLFeedSpider which is the recommended spider to use
for scraping from an XML feed.

See documentation in docs/topics/spiders.rst
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.exceptions import NotConfigured, NotSupported
from scrapy.http import Response, TextResponse
from scrapy.selector import Selector
from scrapy.spiders import Spider
from scrapy.utils.iterators import csviter, xmliter_lxml
from scrapy.utils.spider import iterate_spider_output

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


class XMLFeedSpider(Spider):
    """
    This class intends to be the base class for spiders that scrape
    from XML feeds.

    You can choose whether to parse the file using the 'iternodes' iterator, an
    'xml' selector, or an 'html' selector.  In most cases, it's convenient to
    use iternodes, since it's a faster and cleaner.
    """

    iterator: str = "iternodes"
    itertag: str = "item"
    namespaces: Sequence[tuple[str, str]] = ()

    def process_results(
        self, response: Response, results: Iterable[Any]
    ) -> Iterable[Any]:
        """This overridable method is called for each result (item or request)
        returned by the spider, and it's intended to perform any last time
        processing required before returning the results to the framework core,
        for example setting the item GUIDs. It receives a list of results and
        the response which originated that results. It must return a list of
        results (items or requests).
        """
        return results

    def adapt_response(self, response: Response) -> Response:
        """You can override this function in order to make any changes you want
        to into the feed before parsing it. This function must return a
        response.
        """
        return response

    def parse_node(self, response: Response, selector: Selector) -> Any:
        """This method must be overridden with your custom spider functionality"""
        if hasattr(self, "parse_item"):  # backward compatibility
            return self.parse_item(response, selector)
        raise NotImplementedError

    def parse_nodes(self, response: Response, nodes: Iterable[Selector]) -> Any:
        """This method is called for the nodes matching the provided tag name
        (itertag). Receives the response and an Selector for each node.
        Overriding this method is mandatory. Otherwise, you spider won't work.
        This method must return either an item, a request, or a list
        containing any of them.
        """

        for selector in nodes:
            ret = iterate_spider_output(self.parse_node(response, selector))
            yield from self.process_results(response, ret)

    def _parse(self, response: Response, **kwargs: Any) -> Any:
        if not hasattr(self, "parse_node"):
            raise NotConfigured(
                "You must define parse_node method in order to scrape this XML feed"
            )

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
    It receives a CSV file in a response; iterates through each of its rows,
    and calls parse_row with a dict containing each field's data.

    You can set some options regarding the CSV file, such as the delimiter, quotechar
    and the file's headers.
    """

    delimiter: str | None = (
        None  # When this is None, python's csv module's default delimiter is used
    )
    quotechar: str | None = (
        None  # When this is None, python's csv module's default quotechar is used
    )
    headers: list[str] | None = None

    def process_results(
        self, response: Response, results: Iterable[Any]
    ) -> Iterable[Any]:
        """This method has the same purpose as the one in XMLFeedSpider"""
        return results

    def adapt_response(self, response: Response) -> Response:
        """This method has the same purpose as the one in XMLFeedSpider"""
        return response

    def parse_row(self, response: Response, row: dict[str, str]) -> Any:
        """This method must be overridden with your custom spider functionality"""
        raise NotImplementedError

    def parse_rows(self, response: Response) -> Any:
        """Receives a response and a dict (representing each row) with a key for
        each provided (or detected) header of the CSV file.  This spider also
        gives the opportunity to override adapt_response and
        process_results methods for pre and post-processing purposes.
        """

        for row in csviter(
            response, self.delimiter, self.headers, quotechar=self.quotechar
        ):
            ret = iterate_spider_output(self.parse_row(response, row))
            yield from self.process_results(response, ret)

    def _parse(self, response: Response, **kwargs: Any) -> Any:
        if not hasattr(self, "parse_row"):
            raise NotConfigured(
                "You must define parse_row method in order to scrape this CSV feed"
            )
        response = self.adapt_response(response)
        return self.parse_rows(response)

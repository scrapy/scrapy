"""
This module implements the XMLFeedSpider which is the recommended spider to use
for scraping from an XML feed.

See documentation in docs/topics/spiders.rst
"""
from scrapy.spiders import Spider
from scrapy.utils.iterators import xmliter, csviter
from scrapy.utils.spider import iterate_spider_output
from scrapy.selector import Selector
from scrapy.exceptions import NotConfigured, NotSupported


class XMLFeedSpider(Spider):
    """XMLFeedSpider is designed for parsing XML feeds by iterating through them by a
    certain node name.  The iterator can be chosen from: ``iternodes``, ``xml``,
    and ``html``.  It's recommended to use the ``iternodes`` iterator for
    performance reasons, since the ``xml`` and ``html`` iterators generate the
    whole DOM at once in order to parse it.  However, using ``html`` as the
    iterator may be useful when parsing XML with bad markup.

    To set the iterator and the tag name, you must define the following class
    attributes and overrideable methods:
    """

    #: A string which defines the iterator to use. It can be either:
    #:
    #: - ``'iternodes'`` - a fast iterator based on regular expressions
    #:
    #: - ``'html'`` - an iterator which uses :class:`~scrapy.selector.Selector`.
    #:   Keep in mind this uses DOM parsing and must load all DOM in memory
    #:   which could be a problem for big feeds
    #:
    #: - ``'xml'`` - an iterator which uses :class:`~scrapy.selector.Selector`.
    #:   Keep in mind this uses DOM parsing and must load all DOM in memory
    #:   which could be a problem for big feeds
    #:
    #: It defaults to: ``'iternodes'``.
    iterator = 'iternodes'

    #: A string with the name of the node (or element) to iterate in.
    #:
    #: Example::
    #:
    #:     itertag = 'product'
    itertag = 'item'

    #: A list of ``(prefix, uri)`` tuples which define the namespaces
    #: available in that document that will be processed with this spider. The
    #: ``prefix`` and ``uri`` will be used to automatically register
    #: namespaces using the
    #: :meth:`~scrapy.selector.Selector.register_namespace` method.
    #:
    #: You can then specify nodes with namespaces in the :attr:`itertag`
    #: attribute.
    #:
    #: Example::
    #:
    #:     class YourSpider(XMLFeedSpider):
    #:
    #:         namespaces = [('n', 'http://www.sitemaps.org/schemas/sitemap/0.9')]
    #:         itertag = 'n:url'
    #:         # ...
    namespaces = ()

    def process_results(self, response, results):
        """This method is called for each result (item or request) returned by the
        spider, and it's intended to perform any last time processing required
        before returning the results to the framework core, for example setting the
        item IDs. It receives a list of results and the response which originated
        those results. It must return a list of results (Items or Requests)."""
        return results

    def adapt_response(self, response):
        """A method that receives the response as soon as it arrives from the spider
        middleware, before the spider starts parsing it. It can be used to modify
        the response body before parsing it. This method receives a response and
        also returns a response (it could be the same or another one)."""
        return response

    def parse_node(self, response, selector):
        """This method is called for the nodes matching the provided tag name
        (``itertag``).  Receives the response and an
        :class:`~scrapy.selector.Selector` for each node.  Overriding this
        method is mandatory. Otherwise, you spider won't work.  This method
        must return either a :class:`~scrapy.item.Item` object, a
        :class:`Request <scrapy.Request>` object, or an iterable containing any of
        them."""
        if hasattr(self, 'parse_item'):  # backward compatibility
            return self.parse_item(response, selector)
        raise NotImplementedError

    def parse_nodes(self, response, nodes):
        """This method is called for the nodes matching the provided tag name
        (itertag). Receives the response and an Selector for each node.
        Overriding this method is mandatory. Otherwise, you spider won't work.
        This method must return either a BaseItem, a Request, or a list
        containing any of them.
        """

        for selector in nodes:
            ret = iterate_spider_output(self.parse_node(response, selector))
            for result_item in self.process_results(response, ret):
                yield result_item

    def parse(self, response):
        if not hasattr(self, 'parse_node'):
            raise NotConfigured('You must define parse_node method in order to scrape this XML feed')

        response = self.adapt_response(response)
        if self.iterator == 'iternodes':
            nodes = self._iternodes(response)
        elif self.iterator == 'xml':
            selector = Selector(response, type='xml')
            self._register_namespaces(selector)
            nodes = selector.xpath('//%s' % self.itertag)
        elif self.iterator == 'html':
            selector = Selector(response, type='html')
            self._register_namespaces(selector)
            nodes = selector.xpath('//%s' % self.itertag)
        else:
            raise NotSupported('Unsupported node iterator')

        return self.parse_nodes(response, nodes)

    def _iternodes(self, response):
        for node in xmliter(response, self.itertag):
            self._register_namespaces(node)
            yield node

    def _register_namespaces(self, selector):
        for (prefix, uri) in self.namespaces:
            selector.register_namespace(prefix, uri)


class CSVFeedSpider(Spider):
    """Spider for parsing CSV feeds.

    It receives a CSV file in a response; iterates through each of its rows,
    and calls parse_row with a dict containing each field's data.

    You can set some options regarding the CSV file, such as the delimiter, quotechar
    and the file's headers.
    """

    #: A string with the separator character for each field in the CSV file
    #: Defaults to ``','`` (comma).
    delimiter = None

    #: A string with the enclosure character for each field in the CSV file
    #: Defaults to ``'"'`` (quotation mark).
    quotechar = None

    #: A list of the column names in the CSV file.
    headers = None

    def process_results(self, response, results):
        """This method has the same purpose as the one in XMLFeedSpider"""
        return results

    def adapt_response(self, response):
        """This method has the same purpose as the one in XMLFeedSpider"""
        return response

    def parse_row(self, response, row):
        """Receives a response and a dict (representing each row) with a key for each
        provided (or detected) header of the CSV file.  This spider also gives the
        opportunity to override ``adapt_response`` and ``process_results`` methods
        for pre- and post-processing purposes.

        This method must be overriden with your custom spider functionality
        """
        raise NotImplementedError

    def parse_rows(self, response):
        """Receives a response and a dict (representing each row) with a key for
        each provided (or detected) header of the CSV file.  This spider also
        gives the opportunity to override adapt_response and
        process_results methods for pre and post-processing purposes.
        """

        for row in csviter(response, self.delimiter, self.headers, self.quotechar):
            ret = iterate_spider_output(self.parse_row(response, row))
            for result_item in self.process_results(response, ret):
                yield result_item

    def parse(self, response):
        if not hasattr(self, 'parse_row'):
            raise NotConfigured('You must define parse_row method in order to scrape this CSV feed')
        response = self.adapt_response(response)
        return self.parse_rows(response)


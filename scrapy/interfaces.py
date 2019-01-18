from zope.interface import Interface


class IDownloaderMiddleware(Interface):
    """Interface that any :ref:`downloader middleware
    <topics-downloader-middleware>` class must implement.

    .. note::  Any of the downloader middleware methods may also return a
               deferred.
    """

    def from_crawler(cls, crawler):
        """Optional classmethod that creates an instance of the middleware
        based on the specified :class:`~scrapy.crawler.Crawler`."""

    def process_request(request, spider):
        """This method is called for each request that goes through the
        download middleware.

        It receives a :class:`~scrapy.Request` and a :class:`~scrapy.Spider`,
        and it returns ``None``, a
        :class:`~scrapy.http.Response` or a :class:`~scrapy.Request`,
        or it raises :exc:`~scrapy.exceptions.IgnoreRequest`.

        If it returns ``None``, Scrapy will continue processing *request*,
        executing all other middlewares until, finally, the appropriate
        downloader handler is called, the request performed and its response
        downloaded.

        If it returns a :class:`~scrapy.http.Response`, Scrapy won't
        bother calling any other :meth:`process_request` or
        :meth:`process_exception` method, or the appropriate download function;
        it'll return that response. The :meth:`process_response` methods of
        installed middleware are always called on every response.

        If it returns a :class:`~scrapy.Request`, Scrapy will stop
        calling :meth:`process_request` methods and reschedule the returned
        request. Once the newly returned request is performed, the appropriate
        middleware chain will be called on the downloaded response.

        If it raises an :exc:`~scrapy.exceptions.IgnoreRequest` exception, the
        :meth:`process_exception` methods of installed downloader middleware
        will be called. If none of them handle the exception, the errback
        function of the request (``Request.errback``) is called. If no code
        handles the raised exception, it is ignored and not logged (unlike
        other exceptions).
        """

    def process_response(request, response, spider):
        """:meth:`process_response` should either: return a :class:`~scrapy.http.Response`
        object, return a :class:`~scrapy.Request` object or
        raise a :exc:`~scrapy.exceptions.IgnoreRequest` exception.

        If it returns a :class:`~scrapy.http.Response` (it could be the same given
        response, or a brand-new one), that response will continue to be processed
        with the :meth:`process_response` of the next middleware in the chain.

        If it returns a :class:`~scrapy.Request` object, the middleware chain is
        halted and the returned request is rescheduled to be downloaded in the future.
        This is the same behavior as if a request is returned from :meth:`process_request`.

        If it raises an :exc:`~scrapy.exceptions.IgnoreRequest` exception, the errback
        function of the request (``Request.errback``) is called. If no code handles the raised
        exception, it is ignored and not logged (unlike other exceptions).

        :param request: the request that originated the response
        :type request: is a :class:`~scrapy.Request` object

        :param response: the response being processed
        :type response: :class:`~scrapy.http.Response` object

        :param spider: the spider for which this response is intended
        :type spider: :class:`~scrapy.spiders.Spider` object
        """

    def process_exception(request, exception, spider):
        """Scrapy calls :meth:`process_exception` when a download handler
        or a :meth:`process_request` (from a downloader middleware) raises an
        exception (including an :exc:`~scrapy.exceptions.IgnoreRequest` exception)

        :meth:`process_exception` should return: either ``None``,
        a :class:`~scrapy.http.Response` object, or a :class:`~scrapy.Request` object.

        If it returns ``None``, Scrapy will continue processing this exception,
        executing any other :meth:`process_exception` methods of installed middleware,
        until no middleware is left and the default exception handling kicks in.

        If it returns a :class:`~scrapy.http.Response` object, the :meth:`process_response`
        method chain of installed middleware is started, and Scrapy won't bother calling
        any other :meth:`process_exception` methods of middleware.

        If it returns a :class:`~scrapy.Request` object, the returned request is
        rescheduled to be downloaded in the future. This stops the execution of
        :meth:`process_exception` methods of the middleware the same as returning a
        response would.

        :param request: the request that generated the exception
        :type request: is a :class:`~scrapy.Request` object

        :param exception: the raised exception
        :type exception: Exception

        :param spider: the spider for which this request is intended
        :type spider: :class:`~scrapy.spiders.Spider` object
        """


class IPipeline(Interface):
    """Interface that any :ref:`item pipeline <topics-item-pipeline>` class
    must implement."""

    def process_item(self, item, spider):
        """This method is called for every item pipeline component. :meth:`process_item`
        must either: return a dict with data, return an :class:`~scrapy.item.Item`
        (or any descendant class) object, return a `Twisted Deferred`_ or raise
        :exc:`~scrapy.exceptions.DropItem` exception. Dropped items are no longer
        processed by further pipeline components.

        :param item: the item scraped
        :type item: :class:`~scrapy.item.Item` object or a dict

        :param spider: the spider which scraped the item
        :type spider: :class:`~scrapy.spiders.Spider` object

        .. _Twisted Deferred: https://twistedmatrix.com/documents/current/core/howto/defer.html
        """

    def open_spider(self, spider):
        """Optional method called when the spider is opened.

        :param spider: the spider which was opened
        :type spider: :class:`~scrapy.spiders.Spider` object
        """

    def close_spider(self, spider):
        """Optional method called when the spider is closed.

        :param spider: the spider which was closed
        :type spider: :class:`~scrapy.spiders.Spider` object
        """

    def from_crawler(cls, crawler):
        """If present, this classmethod is called to create a pipeline instance
        from a :class:`~scrapy.crawler.Crawler`. It must return a new instance
        of the pipeline. Crawler object provides access to all Scrapy core
        components like settings and signals; it is a way for pipeline to
        access them and hook its functionality into Scrapy.

        :param crawler: crawler that uses this pipeline
        :type crawler: :class:`~scrapy.crawler.Crawler` object
        """


class ISpiderLoader(Interface):
    """Interface for spider loaders, objects that locate and load the spider
    classes of the project."""

    def from_settings(settings):
        """Return an instance of the class based on the given instance of
        :class:`~scrapy.settings.Settings`."""

    def load(spider_name):
        """Return the :class:`~scrapy.Spider` class for the given
        spider name string.

        If no match is found for *spider_name*, raise a :class:`KeyError`.
        """

    def list():
        """Return a list with the names of all spiders available in the
        project"""

    def find_by_request(request):
        """Return the list of spiders names that can handle the given
        :class:`~scrapy.Request` instance."""


class ISpiderMiddleware(Interface):
    """Interface for :ref:`spider middlewares <topics-spider-middleware>`."""

    def process_spider_input(response, spider):
        """This method is called for each response that goes through the spider
        middleware and into the spider, for processing.

        :meth:`process_spider_input` should return ``None`` or raise an
        exception.

        If it returns ``None``, Scrapy will continue processing this response,
        executing all other middlewares until, finally, the response is handed
        to the spider for processing.

        If it raises an exception, Scrapy won't bother calling any other spider
        middleware :meth:`process_spider_input` and will call the request
        errback.  The output of the errback is chained back in the other
        direction for :meth:`process_spider_output` to process it, or
        :meth:`process_spider_exception` if it raised an exception.

        :param response: the response being processed
        :type response: :class:`~scrapy.http.Response` object

        :param spider: the spider for which this response is intended
        :type spider: :class:`~scrapy.spiders.Spider` object
        """

    def process_spider_output(response, result, spider):
        """This method is called with the results returned from the Spider, after
        it has processed the response.

        :meth:`process_spider_output` must return an iterable of
        :class:`~scrapy.Request`, dict or :class:`~scrapy.item.Item`
        objects.

        :param response: the response which generated this output from the
          spider
        :type response: :class:`~scrapy.http.Response` object

        :param result: the result returned by the spider
        :type result: an iterable of :class:`~scrapy.Request`, dict
          or :class:`~scrapy.item.Item` objects

        :param spider: the spider whose result is being processed
        :type spider: :class:`~scrapy.spiders.Spider` object
        """

    def process_spider_exception(response, exception, spider):
        """This method is called when a spider or :meth:`process_spider_input`
        method (from other spider middleware) raises an exception.

        :meth:`process_spider_exception` should return either ``None`` or an
        iterable of :class:`~scrapy.Request`, dict or
        :class:`~scrapy.item.Item` objects.

        If it returns ``None``, Scrapy will continue processing this exception,
        executing any other :meth:`process_spider_exception` in the following
        middleware components, until no middleware components are left and the
        exception reaches the engine (where it's logged and discarded).

        If it returns an iterable the :meth:`process_spider_output` pipeline
        kicks in, and no other :meth:`process_spider_exception` will be called.

        :param response: the response being processed when the exception was
          raised
        :type response: :class:`~scrapy.http.Response` object

        :param exception: the exception raised
        :type exception: Exception

        :param spider: the spider which raised the exception
        :type spider: :class:`~scrapy.spiders.Spider` object
        """

    def process_start_requests(start_requests, spider):
        """.. versionadded:: 0.15

        This method is called with the start requests of the spider, and works
        similarly to the :meth:`process_spider_output` method, except that it
        doesn't have a response associated and must return only requests (not
        items).

        It receives an iterable (in the ``start_requests`` parameter) and must
        return another iterable of :class:`~scrapy.Request` objects.

        .. note:: When implementing this method in your spider middleware, you
           should always return an iterable (that follows the input one) and
           not consume all ``start_requests`` iterator because it can be very
           large (or even unbounded) and cause a memory overflow. The Scrapy
           engine is designed to pull start requests while it has capacity to
           process them, so the start requests iterator can be effectively
           endless where there is some other condition for stopping the spider
           (like a time limit or item/page count).

        :param start_requests: the start requests
        :type start_requests: an iterable of :class:`~scrapy.Request`

        :param spider: the spider to whom the start requests belong
        :type spider: :class:`~scrapy.spiders.Spider` object
        """

    def from_crawler(cls, crawler):
        """If present, this classmethod is called to create a middleware instance
       from a :class:`~scrapy.crawler.Crawler`. It must return a new instance
       of the middleware. Crawler object provides access to all Scrapy core
       components like settings and signals; it is a way for middleware to
       access them and hook its functionality into Scrapy.

       :param crawler: crawler that uses this middleware
       :type crawler: :class:`~scrapy.crawler.Crawler` object
       """

===========
Spiders API
===========

.. _topics-spiders-ref:

Spiders
=======

.. module:: scrapy.spiders
   :synopsis: Spiders base class, spider manager and spider middleware

.. class:: scrapy.Spider()

   This is the simplest spider, and the one from which every other spider
   must inherit (including spiders that come bundled with Scrapy, as well as spiders
   that you write yourself). It doesn't provide any special functionality. It just
   provides a default :meth:`start_requests` implementation which sends requests from
   the :attr:`start_urls` spider attribute and calls the spider's method ``parse``
   for each of the resulting responses.

   .. attribute:: name

       A string which defines the name for this spider. The spider name is how
       the spider is located (and instantiated) by Scrapy, so it must be
       unique. However, nothing prevents you from instantiating more than one
       instance of the same spider. This is the most important spider attribute
       and it's required.

       If the spider scrapes a single domain, a common practice is to name the
       spider after the domain, with or without the `TLD`_. So, for example, a
       spider that crawls ``mywebsite.com`` would often be called
       ``mywebsite``.

       .. note:: In Python 2 this must be ASCII only.

   .. attribute:: allowed_domains

       An optional list of strings containing domains that this spider is
       allowed to crawl. Requests for URLs not belonging to the domain names
       specified in this list (or their subdomains) won't be followed if
       :class:`~scrapy.spidermiddlewares.offsite.OffsiteMiddleware` is enabled.

       Let's say your target url is ``https://www.example.com/1.html``,
       then add ``'example.com'`` to the list.

   .. attribute:: start_urls

       A list of URLs where the spider will begin to crawl from, when no
       particular URLs are specified. So, the first pages downloaded will be those
       listed here. The subsequent :class:`~scrapy.http.Request` will be generated successively from data
       contained in the start URLs.

   .. attribute:: custom_settings

      A dictionary of settings that will be overridden from the project wide
      configuration when running this spider. It must be defined as a class
      attribute since the settings are updated before instantiation.

      For a list of available built-in settings see:
      :ref:`topics-settings-ref`.

   .. attribute:: crawler

      This attribute is set by the :meth:`from_crawler` class method after
      initializating the class, and links to the
      :class:`~scrapy.crawler.Crawler` object to which this spider instance is
      bound.

      Crawlers encapsulate a lot of components in the project for their single
      entry access (such as extensions, middlewares, signals managers, etc).
      See :ref:`topics-api-crawler` to know more about them.

   .. attribute:: settings

      Configuration for running this spider. This is a
      :class:`~scrapy.settings.Settings` instance, see the
      :ref:`topics-settings` topic for a detailed introduction on this subject.

   .. attribute:: logger

      Python logger created with the Spider's :attr:`name`. You can use it to
      send log messages through it as described on
      :ref:`topics-logging-from-spiders`.

   .. method:: from_crawler(crawler, \*args, \**kwargs)

       This is the class method used by Scrapy to create your spiders.

       You probably won't need to override this directly because the default
       implementation acts as a proxy to the :meth:`__init__` method, calling
       it with the given arguments `args` and named arguments `kwargs`.

       Nonetheless, this method sets the :attr:`crawler` and :attr:`settings`
       attributes in the new instance so they can be accessed later inside the
       spider's code.

       :param crawler: crawler to which the spider will be bound
       :type crawler: :class:`~scrapy.crawler.Crawler` instance

       :param args: arguments passed to the :meth:`__init__` method
       :type args: list

       :param kwargs: keyword arguments passed to the :meth:`__init__` method
       :type kwargs: dict

   .. method:: start_requests()

       This method must return an iterable with the first Requests to crawl for
       this spider. It is called by Scrapy when the spider is opened for
       scraping. Scrapy calls it only once, so it is safe to implement
       :meth:`start_requests` as a generator.

       The default implementation generates ``Request(url, dont_filter=True)``
       for each url in :attr:`start_urls`.

       If you want to change the Requests used to start scraping a domain, this is
       the method to override. For example, if you need to start by logging in using
       a POST request, you could do::

           class MySpider(scrapy.Spider):
               name = 'myspider'

               def start_requests(self):
                   return [scrapy.FormRequest("http://www.example.com/login",
                                              formdata={'user': 'john', 'pass': 'secret'},
                                              callback=self.logged_in)]

               def logged_in(self, response):
                   # here you would extract links to follow and return Requests for
                   # each of them, with another callback
                   pass

   .. method:: parse(response)

       This is the default callback used by Scrapy to process downloaded
       responses, when their requests don't specify a callback.

       The ``parse`` method is in charge of processing the response and returning
       scraped data and/or more URLs to follow. Other Requests callbacks have
       the same requirements as the :class:`Spider` class.

       This method, as well as any other Request callback, must return an
       iterable of :class:`~scrapy.http.Request` and/or
       dicts or :class:`~scrapy.item.Item` objects.

       :param response: the response to parse
       :type response: :class:`~scrapy.http.Response`

   .. method:: log(message, [level, component])

       Wrapper that sends a log message through the Spider's :attr:`logger`,
       kept for backwards compatibility. For more information see
       :ref:`topics-logging-from-spiders`.

   .. method:: closed(reason)

       Called when the spider closes. This method provides a shortcut to
       signals.connect() for the :signal:`spider_closed` signal.

.. class:: scrapy.spiders.Rule(link_extractor, callback=None, cb_kwargs=None, follow=None, process_links=None, process_request=None)

   ``link_extractor`` is a :ref:`Link Extractor <topics-link-extractors>` object which
   defines how links will be extracted from each crawled page.

   ``callback`` is a callable or a string (in which case a method from the spider
   object with that name will be used) to be called for each link extracted with
   the specified link_extractor. This callback receives a response as its first
   argument and must return a list containing :class:`~scrapy.item.Item` and/or
   :class:`~scrapy.http.Request` objects (or any subclass of them).

   .. warning:: When writing crawl spider rules, avoid using ``parse`` as
       callback, since the :class:`CrawlSpider` uses the ``parse`` method
       itself to implement its logic. So if you override the ``parse`` method,
       the crawl spider will no longer work.

   ``cb_kwargs`` is a dict containing the keyword arguments to be passed to the
   callback function.

   ``follow`` is a boolean which specifies if links should be followed from each
   response extracted with this rule. If ``callback`` is None ``follow`` defaults
   to ``True``, otherwise it defaults to ``False``.

   ``process_links`` is a callable, or a string (in which case a method from the
   spider object with that name will be used) which will be called for each list
   of links extracted from each response using the specified ``link_extractor``.
   This is mainly used for filtering purposes.

   ``process_request`` is a callable, or a string (in which case a method from
   the spider object with that name will be used) which will be called with
   every request extracted by this rule, and must return a request or None (to
   filter out the request).

.. class:: scrapy.spiders.CrawlSpider

   This is the most commonly used spider for crawling regular websites, as it
   provides a convenient mechanism for following links by defining a set of rules.
   It may not be the best suited for your particular web sites or project, but
   it's generic enough for several cases, so you can start from it and override it
   as needed for more custom functionality, or just implement your own spider.

   Apart from the attributes inherited from Spider (that you must
   specify), this class supports a new attribute:

   .. attribute:: rules

       Which is a list of one (or more) :class:`Rule` objects.  Each :class:`Rule`
       defines a certain behaviour for crawling the site. Rules objects are
       described below. If multiple rules match the same link, the first one
       will be used, according to the order they're defined in this attribute.

   This spider also exposes an overrideable method:

   .. method:: parse_start_url(response)

      This method is called for the start_urls responses. It allows to parse
      the initial responses and must return either an
      :class:`~scrapy.item.Item` object, a :class:`~scrapy.http.Request`
      object, or an iterable containing any of them.

.. class:: scrapy.spiders.CSVFeedSpider

   This spider is very similar to the XMLFeedSpider, except that it iterates
   over rows, instead of nodes. The method that gets called in each iteration
   is :meth:`parse_row`.

   .. attribute:: delimiter

       A string with the separator character for each field in the CSV file
       Defaults to ``','`` (comma).

   .. attribute:: quotechar

       A string with the enclosure character for each field in the CSV file
       Defaults to ``'"'`` (quotation mark).

   .. attribute:: headers

       A list of the column names in the CSV file.

   .. method:: parse_row(response, row)

       Receives a response and a dict (representing each row) with a key for each
       provided (or detected) header of the CSV file.  This spider also gives the
       opportunity to override ``adapt_response`` and ``process_results`` methods
       for pre- and post-processing purposes.

.. class:: scrapy.spiders.SitemapSpider

    SitemapSpider allows you to crawl a site by discovering the URLs using
    `Sitemaps`_.

    It supports nested sitemaps and discovering sitemap urls from
    `robots.txt`_.

    .. attribute:: sitemap_urls

        A list of urls pointing to the sitemaps whose urls you want to crawl.

        You can also point to a `robots.txt`_ and it will be parsed to extract
        sitemap urls from it.

    .. attribute:: sitemap_rules

        A list of tuples ``(regex, callback)`` where:

        * ``regex`` is a regular expression to match urls extracted from sitemaps.
          ``regex`` can be either a str or a compiled regex object.

        * callback is the callback to use for processing the urls that match
          the regular expression. ``callback`` can be a string (indicating the
          name of a spider method) or a callable.

        For example::

            sitemap_rules = [('/product/', 'parse_product')]

        Rules are applied in order, and only the first one that matches will be
        used.

        If you omit this attribute, all urls found in sitemaps will be
        processed with the ``parse`` callback.

    .. attribute:: sitemap_follow

        A list of regexes of sitemap that should be followed. This is is only
        for sites that use `Sitemap index files`_ that point to other sitemap
        files.

        By default, all sitemaps are followed.

    .. attribute:: sitemap_alternate_links

        Specifies if alternate links for one ``url`` should be followed. These
        are links for the same website in another language passed within
        the same ``url`` block.

        For example::

            <url>
                <loc>http://example.com/</loc>
                <xhtml:link rel="alternate" hreflang="de" href="http://example.com/de"/>
            </url>

        With ``sitemap_alternate_links`` set, this would retrieve both URLs. With
        ``sitemap_alternate_links`` disabled, only ``http://example.com/`` would be
        retrieved.

        Default is ``sitemap_alternate_links`` disabled.

.. class:: scrapy.spiders.XMLFeedSpider

    XMLFeedSpider is designed for parsing XML feeds by iterating through them by a
    certain node name.  The iterator can be chosen from: ``iternodes``, ``xml``,
    and ``html``.  It's recommended to use the ``iternodes`` iterator for
    performance reasons, since the ``xml`` and ``html`` iterators generate the
    whole DOM at once in order to parse it.  However, using ``html`` as the
    iterator may be useful when parsing XML with bad markup.

    To set the iterator and the tag name, you must define the following class
    attributes:

    .. attribute:: iterator

        A string which defines the iterator to use. It can be either:

           - ``'iternodes'`` - a fast iterator based on regular expressions

           - ``'html'`` - an iterator which uses :class:`~scrapy.selector.Selector`.
             Keep in mind this uses DOM parsing and must load all DOM in memory
             which could be a problem for big feeds

           - ``'xml'`` - an iterator which uses :class:`~scrapy.selector.Selector`.
             Keep in mind this uses DOM parsing and must load all DOM in memory
             which could be a problem for big feeds

        It defaults to: ``'iternodes'``.

    .. attribute:: itertag

        A string with the name of the node (or element) to iterate in. Example::

            itertag = 'product'

    .. attribute:: namespaces

        A list of ``(prefix, uri)`` tuples which define the namespaces
        available in that document that will be processed with this spider. The
        ``prefix`` and ``uri`` will be used to automatically register
        namespaces using the
        :meth:`~scrapy.selector.Selector.register_namespace` method.

        You can then specify nodes with namespaces in the :attr:`itertag`
        attribute.

        Example::

            class YourSpider(XMLFeedSpider):

                namespaces = [('n', 'http://www.sitemaps.org/schemas/sitemap/0.9')]
                itertag = 'n:url'
                # ...

    Apart from these new attributes, this spider has the following overrideable
    methods too:

    .. method:: adapt_response(response)

        A method that receives the response as soon as it arrives from the spider
        middleware, before the spider starts parsing it. It can be used to modify
        the response body before parsing it. This method receives a response and
        also returns a response (it could be the same or another one).

    .. method:: parse_node(response, selector)

        This method is called for the nodes matching the provided tag name
        (``itertag``).  Receives the response and an
        :class:`~scrapy.selector.Selector` for each node.  Overriding this
        method is mandatory. Otherwise, you spider won't work.  This method
        must return either a :class:`~scrapy.item.Item` object, a
        :class:`~scrapy.http.Request` object, or an iterable containing any of
        them.

    .. method:: process_results(response, results)

        This method is called for each result (item or request) returned by the
        spider, and it's intended to perform any last time processing required
        before returning the results to the framework core, for example setting the
        item IDs. It receives a list of results and the response which originated
        those results. It must return a list of results (Items or Requests).


Spider Contracts
================

.. module:: scrapy.contracts

.. class:: Contract(method, \*args)

    :param method: callback function to which the contract is associated
    :type method: function

    :param args: list of arguments passed into the docstring (whitespace
        separated)
    :type args: list

    .. method:: Contract.adjust_request_args(args)

        This receives a ``dict`` as an argument containing default arguments
        for request object. :class:`~scrapy.http.Request` is used by default,
        but this can be changed with the ``request_cls`` attribute.
        If multiple contracts in chain have this attribute defined, the last one is used.

        Must return the same or a modified version of it.

    .. method:: Contract.pre_process(response)

        This allows hooking in various checks on the response received from the
        sample request, before it's being passed to the callback.

    .. method:: Contract.post_process(output)

        This allows processing the output of the callback. Iterators are
        converted listified before being passed to this hook.

.. module:: scrapy.contracts.default

.. class:: ReturnsContract

    This contract (``@returns``) sets lower and upper bounds for the items and
    requests returned by the spider. The upper bound is optional::

    @returns item(s)|request(s) [min [max]]

.. class:: ScrapesContract

    This contract (``@scrapes``) checks that all the items returned by the
    callback have the specified fields::

    @scrapes field_1 field_2 ...


.. _robots.txt: http://www.robotstxt.org/
.. _Sitemap index files: https://www.sitemaps.org/protocol.html#index
.. _Sitemaps: https://www.sitemaps.org/index.html
.. _TLD: https://en.wikipedia.org/wiki/Top-level_domain

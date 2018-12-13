===========
Spiders API
===========

.. _topics-spiders-ref:

Spiders
=======

.. module:: scrapy.spiders
   :synopsis: Spiders base class, spider manager and spider middleware

.. class:: Spider()

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


.. _TLD: https://en.wikipedia.org/wiki/Top-level_domain

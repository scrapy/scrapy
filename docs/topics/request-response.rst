.. _topics-request-response:

======================
Requests and Responses
======================

.. module:: scrapy.http
   :synopsis: Request and Response classes

Scrapy uses :class:`Request` and :class:`Response` objects for crawling web
sites.

Typically, :class:`Request` objects are generated in the spiders and pass
across the system until they reach the Downloader, which executes the request
and returns a :class:`Response` object which travels back to the spider that
issued the request.

Both :class:`Request` and :class:`Response` classes have subclasses which add
functionality not required in the base classes. These are described
below in :ref:`topics-request-response-ref-request-subclasses` and
:ref:`topics-request-response-ref-response-subclasses`.


Request objects
===============

.. autoclass:: Request

    :param url: the URL of this request

        If the URL is invalid, a :exc:`ValueError` exception is raised.
    :type url: str

    :param callback: the function that will be called with the response of this
       request (once it's downloaded) as its first parameter.

       In addition to a function, the following values are supported:

       -   ``None`` (default), which indicates that the spider's
           :meth:`~scrapy.Spider.parse` method must be used.

       -   :func:`~scrapy.http.request.NO_CALLBACK`

       For more information, see
       :ref:`topics-request-response-ref-request-callback-arguments`.

       .. note:: If exceptions are raised during processing, ``errback`` is
                 called instead.

    :type callback: collections.abc.Callable

    :param method: the HTTP method of this request. Defaults to ``'GET'``.
    :type method: str

    :param meta: the initial values for the :attr:`Request.meta` attribute. If
       given, the dict passed in this parameter will be shallow copied.
    :type meta: dict

    :param body: the request body. If a string is passed, then it's encoded as
      bytes using the ``encoding`` passed (which defaults to ``utf-8``). If
      ``body`` is not given, an empty bytes object is stored. Regardless of the
      type of this argument, the final value stored will be a bytes object
      (never a string or ``None``).
    :type body: bytes or str

    :param headers: the headers of this request. The dict values can be strings
       (for single valued headers) or lists (for multi-valued headers). If
       ``None`` is passed as value, the HTTP header will not be sent at all.

        .. caution:: Cookies set via the ``Cookie`` header are not considered by the
            :ref:`cookies-mw`. If you need to set cookies for a request, use the
            :class:`Request.cookies <scrapy.Request>` parameter. This is a known
            current limitation that is being worked on.

    :type headers: dict

    :param cookies: the request cookies. These can be sent in two forms.

        .. invisible-code-block: python

            from scrapy.http import Request

        1. Using a dict:

        .. code-block:: python

            request_with_cookies = Request(
                url="http://www.example.com",
                cookies={"currency": "USD", "country": "UY"},
            )

        2. Using a list of dicts:

        .. code-block:: python

            request_with_cookies = Request(
                url="https://www.example.com",
                cookies=[
                    {
                        "name": "currency",
                        "value": "USD",
                        "domain": "example.com",
                        "path": "/currency",
                        "secure": True,
                    },
                ],
            )

        The latter form allows for customizing the ``domain`` and ``path``
        attributes of the cookie. This is only useful if the cookies are saved
        for later requests.

        .. reqmeta:: dont_merge_cookies

        When some site returns cookies (in a response) those are stored in the
        cookies for that domain and will be sent again in future requests.
        That's the typical behaviour of any regular web browser.

        Note that setting the :reqmeta:`dont_merge_cookies` key to ``True`` in
        :attr:`request.meta <scrapy.Request.meta>` causes custom cookies to be
        ignored.

        For more info see :ref:`cookies-mw`.

        .. caution:: Cookies set via the ``Cookie`` header are not considered by the
            :ref:`cookies-mw`. If you need to set cookies for a request, use the
            :class:`Request.cookies <scrapy.Request>` parameter. This is a known
            current limitation that is being worked on.

        .. versionadded:: 2.6.0
           Cookie values that are :class:`bool`, :class:`float` or :class:`int`
           are casted to :class:`str`.

    :type cookies: dict or list

    :param encoding: the encoding of this request (defaults to ``'utf-8'``).
       This encoding will be used to percent-encode the URL and to convert the
       body to bytes (if given as a string).
    :type encoding: str

    :param priority: the priority of this request (defaults to ``0``).
       The priority is used by the scheduler to define the order used to process
       requests.  Requests with a higher priority value will execute earlier.
       Negative values are allowed in order to indicate relatively low-priority.
    :type priority: int

    :param dont_filter: indicates that this request should not be filtered by
       the scheduler. This is used when you want to perform an identical
       request multiple times, to ignore the duplicates filter. Use it with
       care, or you will get into crawling loops. Default to ``False``.
    :type dont_filter: bool

    :param errback: a function that will be called if any exception was
       raised while processing the request. This includes pages that failed
       with 404 HTTP errors and such. It receives a
       :exc:`~twisted.python.failure.Failure` as first parameter.
       For more information,
       see :ref:`topics-request-response-ref-errbacks` below.

       .. versionchanged:: 2.0
          The *callback* parameter is no longer required when the *errback*
          parameter is specified.
    :type errback: collections.abc.Callable

    :param flags:  Flags sent to the request, can be used for logging or similar purposes.
    :type flags: list

    :param cb_kwargs: A dict with arbitrary data that will be passed as keyword arguments to the Request's callback.
    :type cb_kwargs: dict

    .. attribute:: Request.url

        A string containing the URL of this request. Keep in mind that this
        attribute contains the escaped URL, so it can differ from the URL passed in
        the ``__init__`` method.

        This attribute is read-only. To change the URL of a Request use
        :meth:`replace`.

    .. attribute:: Request.method

        A string representing the HTTP method in the request. This is guaranteed to
        be uppercase. Example: ``"GET"``, ``"POST"``, ``"PUT"``, etc

    .. attribute:: Request.headers

        A dictionary-like object which contains the request headers.

    .. attribute:: Request.body

        The request body as bytes.

        This attribute is read-only. To change the body of a Request use
        :meth:`replace`.

    .. attribute:: Request.meta
       :value: {}

        A dictionary of arbitrary metadata for the request.

        You may extend request metadata as you see fit.

        Request metadata can also be accessed through the
        :attr:`~scrapy.http.Response.meta` attribute of a response.

        To pass data from one spider callback to another, consider using
        :attr:`cb_kwargs` instead. However, request metadata may be the right
        choice in certain scenarios, such as to maintain some debugging data
        across all follow-up requests (e.g. the source URL).

        A common use of request metadata is to define request-specific
        parameters for Scrapy components (extensions, middlewares, etc.). For
        example, if you set ``dont_retry`` to ``True``,
        :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware` will never
        retry that request, even if it fails. See :ref:`topics-request-meta`.

        You may also use request metadata in your custom Scrapy components, for
        example, to keep request state information relevant to your component.
        For example,
        :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware` uses the
        ``retry_times`` metadata key to keep track of how many times a request
        has been retried so far.

        Copying all the metadata of a previous request into a new, follow-up
        request in a spider callback is a bad practice, because request
        metadata may include metadata set by Scrapy components that is not
        meant to be copied into other requests. For example, copying the
        ``retry_times`` metadata key into follow-up requests can lower the
        amount of retries allowed for those follow-up requests.

        You should only copy all request metadata from one request to another
        if the new request is meant to replace the old request, as is often the
        case when returning a request from a :ref:`downloader middleware
        <topics-downloader-middleware>` method.

        Also mind that the :meth:`copy` and :meth:`replace` request methods
        :doc:`shallow-copy <library/copy>` request metadata.

    .. attribute:: Request.cb_kwargs

        A dictionary that contains arbitrary metadata for this request. Its contents
        will be passed to the Request's callback as keyword arguments. It is empty
        for new Requests, which means by default callbacks only get a :class:`Response`
        object as argument.

        This dict is :doc:`shallow copied <library/copy>` when the request is
        cloned using the ``copy()`` or ``replace()`` methods, and can also be
        accessed, in your spider, from the ``response.cb_kwargs`` attribute.

        In case of a failure to process the request, this dict can be accessed as
        ``failure.request.cb_kwargs`` in the request's errback. For more information,
        see :ref:`errback-cb_kwargs`.

    .. autoattribute:: Request.attributes

    .. method:: Request.copy()

       Return a new Request which is a copy of this Request. See also:
       :ref:`topics-request-response-ref-request-callback-arguments`.

    .. method:: Request.replace([url, method, headers, body, cookies, meta, flags, encoding, priority, dont_filter, callback, errback, cb_kwargs])

       Return a Request object with the same members, except for those members
       given new values by whichever keyword arguments are specified. The
       :attr:`Request.cb_kwargs` and :attr:`Request.meta` attributes are shallow
       copied by default (unless new values are given as arguments). See also
       :ref:`topics-request-response-ref-request-callback-arguments`.

    .. automethod:: from_curl

    .. automethod:: to_dict


Other functions related to requests
-----------------------------------

.. autofunction:: scrapy.http.request.NO_CALLBACK

.. autofunction:: scrapy.utils.request.request_from_dict


.. _topics-request-response-ref-request-callback-arguments:

Passing additional data to callback functions
---------------------------------------------

The callback of a request is a function that will be called when the response
of that request is downloaded. The callback function will be called with the
downloaded :class:`Response` object as its first argument.

Example:

.. code-block:: python

    def parse_page1(self, response):
        return scrapy.Request(
            "http://www.example.com/some_page.html", callback=self.parse_page2
        )


    def parse_page2(self, response):
        # this would log http://www.example.com/some_page.html
        self.logger.info("Visited %s", response.url)

In some cases you may be interested in passing arguments to those callback
functions so you can receive the arguments later, in the second callback.
The following example shows how to achieve this by using the
:attr:`Request.cb_kwargs` attribute:

.. code-block:: python

    def parse(self, response):
        request = scrapy.Request(
            "http://www.example.com/index.html",
            callback=self.parse_page2,
            cb_kwargs=dict(main_url=response.url),
        )
        request.cb_kwargs["foo"] = "bar"  # add more arguments for the callback
        yield request


    def parse_page2(self, response, main_url, foo):
        yield dict(
            main_url=main_url,
            other_url=response.url,
            foo=foo,
        )

.. caution:: :attr:`Request.cb_kwargs` was introduced in version ``1.7``.
   Prior to that, using :attr:`Request.meta` was recommended for passing
   information around callbacks. After ``1.7``, :attr:`Request.cb_kwargs`
   became the preferred way for handling user information, leaving :attr:`Request.meta`
   for communication with components like middlewares and extensions.

.. _topics-request-response-ref-errbacks:

Using errbacks to catch exceptions in request processing
--------------------------------------------------------

The errback of a request is a function that will be called when an exception
is raise while processing it.

It receives a :exc:`~twisted.python.failure.Failure` as first parameter and can
be used to track connection establishment timeouts, DNS errors etc.

Here's an example spider logging all errors and catching some specific
errors if needed:

.. code-block:: python

    import scrapy

    from scrapy.spidermiddlewares.httperror import HttpError
    from twisted.internet.error import DNSLookupError
    from twisted.internet.error import TimeoutError, TCPTimedOutError


    class ErrbackSpider(scrapy.Spider):
        name = "errback_example"
        start_urls = [
            "http://www.httpbin.org/",  # HTTP 200 expected
            "http://www.httpbin.org/status/404",  # Not found error
            "http://www.httpbin.org/status/500",  # server issue
            "http://www.httpbin.org:12345/",  # non-responding host, timeout expected
            "https://example.invalid/",  # DNS error expected
        ]

        def start_requests(self):
            for u in self.start_urls:
                yield scrapy.Request(
                    u,
                    callback=self.parse_httpbin,
                    errback=self.errback_httpbin,
                    dont_filter=True,
                )

        def parse_httpbin(self, response):
            self.logger.info("Got successful response from {}".format(response.url))
            # do something useful here...

        def errback_httpbin(self, failure):
            # log all failures
            self.logger.error(repr(failure))

            # in case you want to do something special for some errors,
            # you may need the failure's type:

            if failure.check(HttpError):
                # these exceptions come from HttpError spider middleware
                # you can get the non-200 response
                response = failure.value.response
                self.logger.error("HttpError on %s", response.url)

            elif failure.check(DNSLookupError):
                # this is the original request
                request = failure.request
                self.logger.error("DNSLookupError on %s", request.url)

            elif failure.check(TimeoutError, TCPTimedOutError):
                request = failure.request
                self.logger.error("TimeoutError on %s", request.url)


.. _errback-cb_kwargs:

Accessing additional data in errback functions
----------------------------------------------

In case of a failure to process the request, you may be interested in
accessing arguments to the callback functions so you can process further
based on the arguments in the errback. The following example shows how to
achieve this by using ``Failure.request.cb_kwargs``:

.. code-block:: python

    def parse(self, response):
        request = scrapy.Request(
            "http://www.example.com/index.html",
            callback=self.parse_page2,
            errback=self.errback_page2,
            cb_kwargs=dict(main_url=response.url),
        )
        yield request


    def parse_page2(self, response, main_url):
        pass


    def errback_page2(self, failure):
        yield dict(
            main_url=failure.request.cb_kwargs["main_url"],
        )


.. _request-fingerprints:

Request fingerprints
--------------------

There are some aspects of scraping, such as filtering out duplicate requests
(see :setting:`DUPEFILTER_CLASS`) or caching responses (see
:setting:`HTTPCACHE_POLICY`), where you need the ability to generate a short,
unique identifier from a :class:`~scrapy.http.Request` object: a request
fingerprint.

You often do not need to worry about request fingerprints, the default request
fingerprinter works for most projects.

However, there is no universal way to generate a unique identifier from a
request, because different situations require comparing requests differently.
For example, sometimes you may need to compare URLs case-insensitively, include
URL fragments, exclude certain URL query parameters, include some or all
headers, etc.

To change how request fingerprints are built for your requests, use the
:setting:`REQUEST_FINGERPRINTER_CLASS` setting.

.. setting:: REQUEST_FINGERPRINTER_CLASS

REQUEST_FINGERPRINTER_CLASS
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 2.7

Default: :class:`scrapy.utils.request.RequestFingerprinter`

A :ref:`request fingerprinter class <custom-request-fingerprinter>` or its
import path.

.. autoclass:: scrapy.utils.request.RequestFingerprinter

.. _custom-request-fingerprinter:

Writing your own request fingerprinter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A request fingerprinter is a class that must implement the following method:

.. currentmodule:: None

.. method:: fingerprint(self, request)

   Return a :class:`bytes` object that uniquely identifies *request*.

   See also :ref:`request-fingerprint-restrictions`.

   :param request: request to fingerprint
   :type request: scrapy.http.Request

Additionally, it may also implement the following method:

.. classmethod:: from_crawler(cls, crawler)
   :noindex:

   If present, this class method is called to create a request fingerprinter
   instance from a :class:`~scrapy.crawler.Crawler` object. It must return a
   new instance of the request fingerprinter.

   *crawler* provides access to all Scrapy core components like settings and
   signals; it is a way for the request fingerprinter to access them and hook
   its functionality into Scrapy.

   :param crawler: crawler that uses this request fingerprinter
   :type crawler: :class:`~scrapy.crawler.Crawler` object

.. currentmodule:: scrapy.http

The :meth:`fingerprint` method of the default request fingerprinter,
:class:`scrapy.utils.request.RequestFingerprinter`, uses
:func:`scrapy.utils.request.fingerprint` with its default parameters. For some
common use cases you can use :func:`scrapy.utils.request.fingerprint` as well
in your :meth:`fingerprint` method implementation:

.. autofunction:: scrapy.utils.request.fingerprint

For example, to take the value of a request header named ``X-ID`` into
account:

.. code-block:: python

    # my_project/settings.py
    REQUEST_FINGERPRINTER_CLASS = "my_project.utils.RequestFingerprinter"

    # my_project/utils.py
    from scrapy.utils.request import fingerprint


    class RequestFingerprinter:
        def fingerprint(self, request):
            return fingerprint(request, include_headers=["X-ID"])

You can also write your own fingerprinting logic from scratch.

However, if you do not use :func:`scrapy.utils.request.fingerprint`, make sure
you use :class:`~weakref.WeakKeyDictionary` to cache request fingerprints:

-   Caching saves CPU by ensuring that fingerprints are calculated only once
    per request, and not once per Scrapy component that needs the fingerprint
    of a request.

-   Using :class:`~weakref.WeakKeyDictionary` saves memory by ensuring that
    request objects do not stay in memory forever just because you have
    references to them in your cache dictionary.

For example, to take into account only the URL of a request, without any prior
URL canonicalization or taking the request method or body into account:

.. code-block:: python

    from hashlib import sha1
    from weakref import WeakKeyDictionary

    from scrapy.utils.python import to_bytes


    class RequestFingerprinter:
        cache = WeakKeyDictionary()

        def fingerprint(self, request):
            if request not in self.cache:
                fp = sha1()
                fp.update(to_bytes(request.url))
                self.cache[request] = fp.digest()
            return self.cache[request]

If you need to be able to override the request fingerprinting for arbitrary
requests from your spider callbacks, you may implement a request fingerprinter
that reads fingerprints from :attr:`request.meta <scrapy.http.Request.meta>`
when available, and then falls back to
:func:`scrapy.utils.request.fingerprint`. For example:

.. code-block:: python

    from scrapy.utils.request import fingerprint


    class RequestFingerprinter:
        def fingerprint(self, request):
            if "fingerprint" in request.meta:
                return request.meta["fingerprint"]
            return fingerprint(request)

If you need to reproduce the same fingerprinting algorithm as Scrapy 2.6
without using the deprecated ``'2.6'`` value of the
:setting:`REQUEST_FINGERPRINTER_IMPLEMENTATION` setting, use the following
request fingerprinter:

.. code-block:: python

    from hashlib import sha1
    from weakref import WeakKeyDictionary

    from scrapy.utils.python import to_bytes
    from w3lib.url import canonicalize_url


    class RequestFingerprinter:
        cache = WeakKeyDictionary()

        def fingerprint(self, request):
            if request not in self.cache:
                fp = sha1()
                fp.update(to_bytes(request.method))
                fp.update(to_bytes(canonicalize_url(request.url)))
                fp.update(request.body or b"")
                self.cache[request] = fp.digest()
            return self.cache[request]


.. _request-fingerprint-restrictions:

Request fingerprint restrictions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Scrapy components that use request fingerprints may impose additional
restrictions on the format of the fingerprints that your :ref:`request
fingerprinter <custom-request-fingerprinter>` generates.

The following built-in Scrapy components have such restrictions:

-   :class:`scrapy.extensions.httpcache.FilesystemCacheStorage` (default
    value of :setting:`HTTPCACHE_STORAGE`)

    Request fingerprints must be at least 1 byte long.

    Path and filename length limits of the file system of
    :setting:`HTTPCACHE_DIR` also apply. Inside :setting:`HTTPCACHE_DIR`,
    the following directory structure is created:

    -   :attr:`Spider.name <scrapy.spiders.Spider.name>`

        -   first byte of a request fingerprint as hexadecimal

            -   fingerprint as hexadecimal

                -   filenames up to 16 characters long

    For example, if a request fingerprint is made of 20 bytes (default),
    :setting:`HTTPCACHE_DIR` is ``'/home/user/project/.scrapy/httpcache'``,
    and the name of your spider is ``'my_spider'`` your file system must
    support a file path like::

        /home/user/project/.scrapy/httpcache/my_spider/01/0123456789abcdef0123456789abcdef01234567/response_headers

-   :class:`scrapy.extensions.httpcache.DbmCacheStorage`

    The underlying DBM implementation must support keys as long as twice
    the number of bytes of a request fingerprint, plus 5. For example,
    if a request fingerprint is made of 20 bytes (default),
    45-character-long keys must be supported.


.. _topics-request-meta:

Request.meta special keys
=========================

The :attr:`Request.meta` attribute can contain any arbitrary data, but there
are some special keys recognized by Scrapy and its built-in extensions.

Those are:

* :reqmeta:`autothrottle_dont_adjust_delay`
* :reqmeta:`bindaddress`
* :reqmeta:`cookiejar`
* :reqmeta:`dont_cache`
* :reqmeta:`dont_merge_cookies`
* :reqmeta:`dont_obey_robotstxt`
* :reqmeta:`dont_redirect`
* :reqmeta:`dont_retry`
* :reqmeta:`download_fail_on_dataloss`
* :reqmeta:`download_latency`
* :reqmeta:`download_maxsize`
* :reqmeta:`download_warnsize`
* :reqmeta:`download_timeout`
* ``ftp_password`` (See :setting:`FTP_PASSWORD` for more info)
* ``ftp_user`` (See :setting:`FTP_USER` for more info)
* :reqmeta:`handle_httpstatus_all`
* :reqmeta:`handle_httpstatus_list`
* :reqmeta:`max_retry_times`
* :reqmeta:`proxy`
* :reqmeta:`redirect_reasons`
* :reqmeta:`redirect_urls`
* :reqmeta:`referrer_policy`

.. reqmeta:: bindaddress

bindaddress
-----------

The IP of the outgoing IP address to use for the performing the request.

.. reqmeta:: download_timeout

download_timeout
----------------

The amount of time (in secs) that the downloader will wait before timing out.
See also: :setting:`DOWNLOAD_TIMEOUT`.

.. reqmeta:: download_latency

download_latency
----------------

The amount of time spent to fetch the response, since the request has been
started, i.e. HTTP message sent over the network. This meta key only becomes
available when the response has been downloaded. While most other meta keys are
used to control Scrapy behavior, this one is supposed to be read-only.

.. reqmeta:: download_fail_on_dataloss

download_fail_on_dataloss
-------------------------

Whether or not to fail on broken responses. See:
:setting:`DOWNLOAD_FAIL_ON_DATALOSS`.

.. reqmeta:: max_retry_times

max_retry_times
---------------

The meta key is used set retry times per request. When initialized, the
:reqmeta:`max_retry_times` meta key takes higher precedence over the
:setting:`RETRY_TIMES` setting.


.. _topics-stop-response-download:

Stopping the download of a Response
===================================

Raising a :exc:`~scrapy.exceptions.StopDownload` exception from a handler for the
:class:`~scrapy.signals.bytes_received` or :class:`~scrapy.signals.headers_received`
signals will stop the download of a given response. See the following example:

.. code-block:: python

    import scrapy


    class StopSpider(scrapy.Spider):
        name = "stop"
        start_urls = ["https://docs.scrapy.org/en/latest/"]

        @classmethod
        def from_crawler(cls, crawler):
            spider = super().from_crawler(crawler)
            crawler.signals.connect(
                spider.on_bytes_received, signal=scrapy.signals.bytes_received
            )
            return spider

        def parse(self, response):
            # 'last_chars' show that the full response was not downloaded
            yield {"len": len(response.text), "last_chars": response.text[-40:]}

        def on_bytes_received(self, data, request, spider):
            raise scrapy.exceptions.StopDownload(fail=False)

which produces the following output::

    2020-05-19 17:26:12 [scrapy.core.engine] INFO: Spider opened
    2020-05-19 17:26:12 [scrapy.extensions.logstats] INFO: Crawled 0 pages (at 0 pages/min), scraped 0 items (at 0 items/min)
    2020-05-19 17:26:13 [scrapy.core.downloader.handlers.http11] DEBUG: Download stopped for <GET https://docs.scrapy.org/en/latest/> from signal handler StopSpider.on_bytes_received
    2020-05-19 17:26:13 [scrapy.core.engine] DEBUG: Crawled (200) <GET https://docs.scrapy.org/en/latest/> (referer: None) ['download_stopped']
    2020-05-19 17:26:13 [scrapy.core.scraper] DEBUG: Scraped from <200 https://docs.scrapy.org/en/latest/>
    {'len': 279, 'last_chars': 'dth, initial-scale=1.0">\n  \n  <title>Scr'}
    2020-05-19 17:26:13 [scrapy.core.engine] INFO: Closing spider (finished)

By default, resulting responses are handled by their corresponding errbacks. To
call their callback instead, like in this example, pass ``fail=False`` to the
:exc:`~scrapy.exceptions.StopDownload` exception.


.. _topics-request-response-ref-request-subclasses:

Request subclasses
==================

Here is the list of built-in :class:`Request` subclasses. You can also subclass
it to implement your own custom functionality.

FormRequest objects
-------------------

The FormRequest class extends the base :class:`Request` with functionality for
dealing with HTML forms. It uses `lxml.html forms`_  to pre-populate form
fields with form data from :class:`Response` objects.

.. _lxml.html forms: https://lxml.de/lxmlhtml.html#forms

.. class:: scrapy.http.request.form.FormRequest
.. class:: scrapy.http.FormRequest
.. class:: scrapy.FormRequest(url, [formdata, ...])

    The :class:`FormRequest` class adds a new keyword parameter to the ``__init__`` method. The
    remaining arguments are the same as for the :class:`Request` class and are
    not documented here.

    :param formdata: is a dictionary (or iterable of (key, value) tuples)
       containing HTML Form data which will be url-encoded and assigned to the
       body of the request.
    :type formdata: dict or collections.abc.Iterable

    The :class:`FormRequest` objects support the following class method in
    addition to the standard :class:`Request` methods:

    .. classmethod:: FormRequest.from_response(response, [formname=None, formid=None, formnumber=0, formdata=None, formxpath=None, formcss=None, clickdata=None, dont_click=False, ...])

       Returns a new :class:`FormRequest` object with its form field values
       pre-populated with those found in the HTML ``<form>`` element contained
       in the given response. For an example see
       :ref:`topics-request-response-ref-request-userlogin`.

       The policy is to automatically simulate a click, by default, on any form
       control that looks clickable, like a ``<input type="submit">``.  Even
       though this is quite convenient, and often the desired behaviour,
       sometimes it can cause problems which could be hard to debug. For
       example, when working with forms that are filled and/or submitted using
       javascript, the default :meth:`from_response` behaviour may not be the
       most appropriate. To disable this behaviour you can set the
       ``dont_click`` argument to ``True``. Also, if you want to change the
       control clicked (instead of disabling it) you can also use the
       ``clickdata`` argument.

       .. caution:: Using this method with select elements which have leading
          or trailing whitespace in the option values will not work due to a
          `bug in lxml`_, which should be fixed in lxml 3.8 and above.

       :param response: the response containing a HTML form which will be used
          to pre-populate the form fields
       :type response: :class:`Response` object

       :param formname: if given, the form with name attribute set to this value will be used.
       :type formname: str

       :param formid: if given, the form with id attribute set to this value will be used.
       :type formid: str

       :param formxpath: if given, the first form that matches the xpath will be used.
       :type formxpath: str

       :param formcss: if given, the first form that matches the css selector will be used.
       :type formcss: str

       :param formnumber: the number of form to use, when the response contains
          multiple forms. The first one (and also the default) is ``0``.
       :type formnumber: int

       :param formdata: fields to override in the form data. If a field was
          already present in the response ``<form>`` element, its value is
          overridden by the one passed in this parameter. If a value passed in
          this parameter is ``None``, the field will not be included in the
          request, even if it was present in the response ``<form>`` element.
       :type formdata: dict

       :param clickdata: attributes to lookup the control clicked. If it's not
         given, the form data will be submitted simulating a click on the
         first clickable element. In addition to html attributes, the control
         can be identified by its zero-based index relative to other
         submittable inputs inside the form, via the ``nr`` attribute.
       :type clickdata: dict

       :param dont_click: If True, the form data will be submitted without
         clicking in any element.
       :type dont_click: bool

       The other parameters of this class method are passed directly to the
       :class:`FormRequest` ``__init__`` method.

Request usage examples
----------------------

Using FormRequest to send data via HTTP POST
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to simulate a HTML Form POST in your spider and send a couple of
key-value fields, you can return a :class:`FormRequest` object (from your
spider) like this:

.. skip: next
.. code-block:: python

   return [
       FormRequest(
           url="http://www.example.com/post/action",
           formdata={"name": "John Doe", "age": "27"},
           callback=self.after_post,
       )
   ]

.. _topics-request-response-ref-request-userlogin:

Using FormRequest.from_response() to simulate a user login
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is usual for web sites to provide pre-populated form fields through ``<input
type="hidden">`` elements, such as session related data or authentication
tokens (for login pages). When scraping, you'll want these fields to be
automatically pre-populated and only override a couple of them, such as the
user name and password. You can use the :meth:`FormRequest.from_response`
method for this job. Here's an example spider which uses it:

.. code-block:: python

    import scrapy


    def authentication_failed(response):
        # TODO: Check the contents of the response and return True if it failed
        # or False if it succeeded.
        pass


    class LoginSpider(scrapy.Spider):
        name = "example.com"
        start_urls = ["http://www.example.com/users/login.php"]

        def parse(self, response):
            return scrapy.FormRequest.from_response(
                response,
                formdata={"username": "john", "password": "secret"},
                callback=self.after_login,
            )

        def after_login(self, response):
            if authentication_failed(response):
                self.logger.error("Login failed")
                return

            # continue scraping with authenticated session...

JsonRequest
-----------

The JsonRequest class extends the base :class:`Request` class with functionality for
dealing with JSON requests.

.. class:: JsonRequest(url, [... data, dumps_kwargs])

   The :class:`JsonRequest` class adds two new keyword parameters to the ``__init__`` method. The
   remaining arguments are the same as for the :class:`Request` class and are
   not documented here.

   Using the :class:`JsonRequest` will set the ``Content-Type`` header to ``application/json``
   and ``Accept`` header to ``application/json, text/javascript, */*; q=0.01``

   :param data: is any JSON serializable object that needs to be JSON encoded and assigned to body.
      if :attr:`Request.body` argument is provided this parameter will be ignored.
      if :attr:`Request.body` argument is not provided and data argument is provided :attr:`Request.method` will be
      set to ``'POST'`` automatically.
   :type data: object

   :param dumps_kwargs: Parameters that will be passed to underlying :func:`json.dumps` method which is used to serialize
       data into JSON format.
   :type dumps_kwargs: dict

   .. autoattribute:: JsonRequest.attributes

JsonRequest usage example
-------------------------

Sending a JSON POST request with a JSON payload:

.. skip: next
.. code-block:: python

   data = {
       "name1": "value1",
       "name2": "value2",
   }
   yield JsonRequest(url="http://www.example.com/post/action", data=data)


Response objects
================

.. autoclass:: Response

    :param url: the URL of this response
    :type url: str

    :param status: the HTTP status of the response. Defaults to ``200``.
    :type status: int

    :param headers: the headers of this response. The dict values can be strings
       (for single valued headers) or lists (for multi-valued headers).
    :type headers: dict

    :param body: the response body. To access the decoded text as a string, use
       ``response.text`` from an encoding-aware
       :ref:`Response subclass <topics-request-response-ref-response-subclasses>`,
       such as :class:`TextResponse`.
    :type body: bytes

    :param flags: is a list containing the initial values for the
       :attr:`Response.flags` attribute. If given, the list will be shallow
       copied.
    :type flags: list

    :param request: the initial value of the :attr:`Response.request` attribute.
        This represents the :class:`Request` that generated this response.
    :type request: scrapy.Request

    :param certificate: an object representing the server's SSL certificate.
    :type certificate: twisted.internet.ssl.Certificate

    :param ip_address: The IP address of the server from which the Response originated.
    :type ip_address: :class:`ipaddress.IPv4Address` or :class:`ipaddress.IPv6Address`

    :param protocol: The protocol that was used to download the response.
        For instance: "HTTP/1.0", "HTTP/1.1", "h2"
    :type protocol: :class:`str`

    .. versionadded:: 2.0.0
       The ``certificate`` parameter.

    .. versionadded:: 2.1.0
       The ``ip_address`` parameter.

    .. versionadded:: 2.5.0
       The ``protocol`` parameter.

    .. attribute:: Response.url

        A string containing the URL of the response.

        This attribute is read-only. To change the URL of a Response use
        :meth:`replace`.

    .. attribute:: Response.status

        An integer representing the HTTP status of the response. Example: ``200``,
        ``404``.

    .. attribute:: Response.headers

        A dictionary-like object which contains the response headers. Values can
        be accessed using :meth:`get` to return the first header value with the
        specified name or :meth:`getlist` to return all header values with the
        specified name. For example, this call will give you all cookies in the
        headers::

            response.headers.getlist('Set-Cookie')

    .. attribute:: Response.body

        The response body as bytes.

        If you want the body as a string, use :attr:`TextResponse.text` (only
        available in :class:`TextResponse` and subclasses).

        This attribute is read-only. To change the body of a Response use
        :meth:`replace`.

    .. attribute:: Response.request

        The :class:`Request` object that generated this response. This attribute is
        assigned in the Scrapy engine, after the response and the request have passed
        through all :ref:`Downloader Middlewares <topics-downloader-middleware>`.
        In particular, this means that:

        - HTTP redirections will create a new request from the request before
          redirection. It has the majority of the same metadata and original
          request attributes and gets assigned to the redirected response
          instead of the propagation of the original request.

        - Response.request.url doesn't always equal Response.url

        - This attribute is only available in the spider code, and in the
          :ref:`Spider Middlewares <topics-spider-middleware>`, but not in
          Downloader Middlewares (although you have the Request available there by
          other means) and handlers of the :signal:`response_downloaded` signal.

    .. attribute:: Response.meta

        A shortcut to the :attr:`Request.meta` attribute of the
        :attr:`Response.request` object (i.e. ``self.request.meta``).

        Unlike the :attr:`Response.request` attribute, the :attr:`Response.meta`
        attribute is propagated along redirects and retries, so you will get
        the original :attr:`Request.meta` sent from your spider.

        .. seealso:: :attr:`Request.meta` attribute

    .. attribute:: Response.cb_kwargs

        .. versionadded:: 2.0

        A shortcut to the :attr:`Request.cb_kwargs` attribute of the
        :attr:`Response.request` object (i.e. ``self.request.cb_kwargs``).

        Unlike the :attr:`Response.request` attribute, the
        :attr:`Response.cb_kwargs` attribute is propagated along redirects and
        retries, so you will get the original :attr:`Request.cb_kwargs` sent
        from your spider.

        .. seealso:: :attr:`Request.cb_kwargs` attribute

    .. attribute:: Response.flags

        A list that contains flags for this response. Flags are labels used for
        tagging Responses. For example: ``'cached'``, ``'redirected``', etc. And
        they're shown on the string representation of the Response (`__str__`
        method) which is used by the engine for logging.

    .. attribute:: Response.certificate

        .. versionadded:: 2.0.0

        A :class:`twisted.internet.ssl.Certificate` object representing
        the server's SSL certificate.

        Only populated for ``https`` responses, ``None`` otherwise.

    .. attribute:: Response.ip_address

        .. versionadded:: 2.1.0

        The IP address of the server from which the Response originated.

        This attribute is currently only populated by the HTTP 1.1 download
        handler, i.e. for ``http(s)`` responses. For other handlers,
        :attr:`ip_address` is always ``None``.

    .. attribute:: Response.protocol

        .. versionadded:: 2.5.0

        The protocol that was used to download the response.
        For instance: "HTTP/1.0", "HTTP/1.1"

        This attribute is currently only populated by the HTTP download
        handlers, i.e. for ``http(s)`` responses. For other handlers,
        :attr:`protocol` is always ``None``.

    .. autoattribute:: Response.attributes

    .. method:: Response.copy()

       Returns a new Response which is a copy of this Response.

    .. method:: Response.replace([url, status, headers, body, request, flags, cls])

       Returns a Response object with the same members, except for those members
       given new values by whichever keyword arguments are specified. The
       attribute :attr:`Response.meta` is copied by default.

    .. method:: Response.urljoin(url)

        Constructs an absolute url by combining the Response's :attr:`url` with
        a possible relative url.

        This is a wrapper over :func:`~urllib.parse.urljoin`, it's merely an alias for
        making this call::

            urllib.parse.urljoin(response.url, url)

    .. automethod:: Response.follow

    .. automethod:: Response.follow_all


.. _topics-request-response-ref-response-subclasses:

Response subclasses
===================

Here is the list of available built-in Response subclasses. You can also
subclass the Response class to implement your own functionality.

TextResponse objects
--------------------

.. class:: TextResponse(url, [encoding[, ...]])

    :class:`TextResponse` objects adds encoding capabilities to the base
    :class:`Response` class, which is meant to be used only for binary data,
    such as images, sounds or any media file.

    :class:`TextResponse` objects support a new ``__init__`` method argument, in
    addition to the base :class:`Response` objects. The remaining functionality
    is the same as for the :class:`Response` class and is not documented here.

    :param encoding: is a string which contains the encoding to use for this
       response. If you create a :class:`TextResponse` object with a string as
       body, it will be converted to bytes encoded using this encoding. If
       *encoding* is ``None`` (default), the encoding will be looked up in the
       response headers and body instead.
    :type encoding: str

    :class:`TextResponse` objects support the following attributes in addition
    to the standard :class:`Response` ones:

    .. attribute:: TextResponse.text

       Response body, as a string.

       The same as ``response.body.decode(response.encoding)``, but the
       result is cached after the first call, so you can access
       ``response.text`` multiple times without extra overhead.

       .. note::

            ``str(response.body)`` is not a correct way to convert the response
            body into a string:

            .. code-block:: pycon

                >>> str(b"body")
                "b'body'"


    .. attribute:: TextResponse.encoding

       A string with the encoding of this response. The encoding is resolved by
       trying the following mechanisms, in order:

       1. the encoding passed in the ``__init__`` method ``encoding`` argument

       2. the encoding declared in the Content-Type HTTP header. If this
          encoding is not valid (i.e. unknown), it is ignored and the next
          resolution mechanism is tried.

       3. the encoding declared in the response body. The TextResponse class
          doesn't provide any special functionality for this. However, the
          :class:`HtmlResponse` and :class:`XmlResponse` classes do.

       4. the encoding inferred by looking at the response body. This is the more
          fragile method but also the last one tried.

    .. attribute:: TextResponse.selector

        A :class:`~scrapy.Selector` instance using the response as
        target. The selector is lazily instantiated on first access.

    .. autoattribute:: TextResponse.attributes

    :class:`TextResponse` objects support the following methods in addition to
    the standard :class:`Response` ones:

    .. method:: TextResponse.jmespath(query)

        A shortcut to ``TextResponse.selector.jmespath(query)``::

            response.jmespath('object.[*]')

    .. method:: TextResponse.xpath(query)

        A shortcut to ``TextResponse.selector.xpath(query)``::

            response.xpath('//p')

    .. method:: TextResponse.css(query)

        A shortcut to ``TextResponse.selector.css(query)``::

            response.css('p')

    .. automethod:: TextResponse.follow

    .. automethod:: TextResponse.follow_all

    .. automethod:: TextResponse.json()

        Returns a Python object from deserialized JSON document.
        The result is cached after the first call.

    .. method:: TextResponse.urljoin(url)

        Constructs an absolute url by combining the Response's base url with
        a possible relative url. The base url shall be extracted from the
        ``<base>`` tag, or just the Response's :attr:`url` if there is no such
        tag.



HtmlResponse objects
--------------------

.. class:: HtmlResponse(url[, ...])

    The :class:`HtmlResponse` class is a subclass of :class:`TextResponse`
    which adds encoding auto-discovering support by looking into the HTML `meta
    http-equiv`_ attribute.  See :attr:`TextResponse.encoding`.

.. _meta http-equiv: https://www.w3schools.com/TAGS/att_meta_http_equiv.asp

XmlResponse objects
-------------------

.. class:: XmlResponse(url[, ...])

    The :class:`XmlResponse` class is a subclass of :class:`TextResponse` which
    adds encoding auto-discovering support by looking into the XML declaration
    line.  See :attr:`TextResponse.encoding`.

.. _bug in lxml: https://bugs.launchpad.net/lxml/+bug/1665241

JsonResponse objects
--------------------

.. class:: JsonResponse(url[, ...])

    The :class:`JsonResponse` class is a subclass of :class:`TextResponse` 
    that is used when the response has a `JSON MIME type 
    <https://mimesniff.spec.whatwg.org/#json-mime-type>`_ in its `Content-Type` 
    header.

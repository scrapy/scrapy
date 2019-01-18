.. currentmodule:: scrapy

.. _topics-request-response:

======================
Requests and Responses
======================

Scrapy uses :class:`Request` and :class:`~http.Response` objects for
crawling web sites.

Typically, :class:`Request` objects are generated in the spiders and pass
across the system until they reach the Downloader, which executes the request
and returns a :class:`~http.Response` object which travels back to the
spider that issued the request.

Both :class:`Request` and :class:`~http.Response` classes have
subclasses which add functionality not required in the base classes. These are
described below in :ref:`topics-request-response-ref-request-subclasses` and
:ref:`topics-request-response-ref-response-subclasses`.

Requests
========

.. _topics-request-response-ref-request-callback-arguments:

Passing additional data to callback functions
---------------------------------------------

The callback of a request is a function that will be called when the response
of that request is downloaded. The callback function will be called with the
downloaded :class:`~http.Response` object as its first argument.

Example::

    def parse_page1(self, response):
        return scrapy.Request("http://www.example.com/some_page.html",
                              callback=self.parse_page2)

    def parse_page2(self, response):
        # this would log http://www.example.com/some_page.html
        self.logger.info("Visited %s", response.url)

In some cases you may be interested in passing arguments to those callback
functions so you can receive the arguments later, in the second callback. You
can use the :attr:`Request.meta` attribute for that.

Here's an example of how to pass an item using this mechanism, to populate
different fields from different pages::

    def parse_page1(self, response):
        item = MyItem()
        item['main_url'] = response.url
        request = scrapy.Request("http://www.example.com/some_page.html",
                                 callback=self.parse_page2)
        request.meta['item'] = item
        yield request

    def parse_page2(self, response):
        item = response.meta['item']
        item['other_url'] = response.url
        yield item


.. _topics-request-response-ref-errbacks:

Using errbacks to catch exceptions in request processing
--------------------------------------------------------

The errback of a request is a function that will be called when an exception
is raise while processing it.

It receives a `Twisted Failure`_ instance as first parameter and can be
used to track connection establishment timeouts, DNS errors etc.

Here's an example spider logging all errors and catching some specific
errors if needed::

    import scrapy

    from scrapy.spidermiddlewares.httperror import HttpError
    from twisted.internet.error import DNSLookupError
    from twisted.internet.error import TimeoutError, TCPTimedOutError

    class ErrbackSpider(scrapy.Spider):
        name = "errback_example"
        start_urls = [
            "http://www.httpbin.org/",              # HTTP 200 expected
            "http://www.httpbin.org/status/404",    # Not found error
            "http://www.httpbin.org/status/500",    # server issue
            "http://www.httpbin.org:12345/",        # non-responding host, timeout expected
            "http://www.httphttpbinbin.org/",       # DNS error expected
        ]

        def start_requests(self):
            for u in self.start_urls:
                yield scrapy.Request(u, callback=self.parse_httpbin,
                                        errback=self.errback_httpbin,
                                        dont_filter=True)

        def parse_httpbin(self, response):
            self.logger.info('Got successful response from {}'.format(response.url))
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
                self.logger.error('HttpError on %s', response.url)

            elif failure.check(DNSLookupError):
                # this is the original request
                request = failure.request
                self.logger.error('DNSLookupError on %s', request.url)

            elif failure.check(TimeoutError, TCPTimedOutError):
                request = failure.request
                self.logger.error('TimeoutError on %s', request.url)

.. _topics-request-meta:

Request.meta special keys
=========================

The :attr:`Request.meta` attribute can contain any arbitrary data, but there
are some special keys recognized by Scrapy and its built-in extensions.

Those are:

* :reqmeta:`dont_redirect`
* :reqmeta:`dont_retry`
* :reqmeta:`handle_httpstatus_list`
* :reqmeta:`handle_httpstatus_all`
* :reqmeta:`dont_merge_cookies`
* :reqmeta:`cookiejar`
* :reqmeta:`dont_cache`
* :reqmeta:`redirect_urls`
* :reqmeta:`bindaddress`
* :reqmeta:`dont_obey_robotstxt`
* :reqmeta:`download_timeout`
* :reqmeta:`download_maxsize`
* :reqmeta:`download_latency`
* :reqmeta:`download_fail_on_dataloss`
* :reqmeta:`proxy`
* ``ftp_user`` (See :setting:`FTP_USER` for more info)
* ``ftp_password`` (See :setting:`FTP_PASSWORD` for more info)
* :reqmeta:`referrer_policy`
* :reqmeta:`max_retry_times`

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

.. _topics-request-response-ref-request-subclasses:

Request subclasses
==================

Here is the list of built-in :class:`Request` subclasses. You can also subclass
it to implement your own custom functionality.

FormRequest
-----------

The :class:`FormRequest` class extends the base :class:`Request` with
functionality for dealing with HTML forms. It uses `lxml.html forms`_  to
pre-populate form fields with form data from :class:`~http.Response`
objects.

.. _lxml.html forms: http://lxml.de/lxmlhtml.html#forms

Request usage examples
----------------------

Using FormRequest to send data via HTTP POST
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to simulate a HTML Form POST in your spider and send a couple of
key-value fields, you can return a :class:`FormRequest` object (from your
spider) like this::

   return [FormRequest(url="http://www.example.com/post/action",
                       formdata={'name': 'John Doe', 'age': '27'},
                       callback=self.after_post)]

.. _topics-request-response-ref-request-userlogin:

Using FormRequest.from_response() to simulate a user login
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is usual for web sites to provide pre-populated form fields through ``<input
type="hidden">`` elements, such as session related data or authentication
tokens (for login pages). When scraping, you'll want these fields to be
automatically pre-populated and only override a couple of them, such as the
user name and password. You can use the :meth:`FormRequest.from_response`
method for this job. Here's an example spider which uses it::


    import scrapy

    class LoginSpider(scrapy.Spider):
        name = 'example.com'
        start_urls = ['http://www.example.com/users/login.php']

        def parse(self, response):
            return scrapy.FormRequest.from_response(
                response,
                formdata={'username': 'john', 'password': 'secret'},
                callback=self.after_login
            )

        def after_login(self, response):
            # check login succeed before going on
            if "authentication failed" in response.body:
                self.logger.error("Login failed")
                return

            # continue scraping with authenticated session...

.. _topics-request-response-ref-response-subclasses:

Response subclasses
===================

Scrapy provides the following built-in Response subclasses:
:class:`~http.TextResponse`, :class:`~http.HtmlResponse`,
:class:`~http.XmlResponse`. You can also subclass the
:class:`~http.Response` class to implement your own functionality.


.. _Twisted Failure: https://twistedmatrix.com/documents/current/api/twisted.python.failure.Failure.html

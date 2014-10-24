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

.. class:: Request(url[, callback, method='GET', headers, body, cookies, meta, encoding='utf-8', priority=0, dont_filter=False, errback])

    A :class:`Request` object represents an HTTP request, which is usually
    generated in the Spider and executed by the Downloader, and thus generating
    a :class:`Response`.

    :param url: the URL of this request
    :type url: string

    :param callback: the function that will be called with the response of this
       request (once its downloaded) as its first parameter. For more information
       see :ref:`topics-request-response-ref-request-callback-arguments` below.
       If a Request doesn't specify a callback, the spider's
       :meth:`~scrapy.spider.Spider.parse` method will be used.
       Note that if exceptions are raised during processing, errback is called instead.

    :type callback: callable

    :param method: the HTTP method of this request. Defaults to ``'GET'``.
    :type method: string

    :param meta: the initial values for the :attr:`Request.meta` attribute. If
       given, the dict passed in this parameter will be shallow copied.
    :type meta: dict

    :param body: the request body. If a ``unicode`` is passed, then it's encoded to
      ``str`` using the `encoding` passed (which defaults to ``utf-8``). If
      ``body`` is not given, an empty string is stored. Regardless of the
      type of this argument, the final value stored will be a ``str`` (never
      ``unicode`` or ``None``).
    :type body: str or unicode

    :param headers: the headers of this request. The dict values can be strings
       (for single valued headers) or lists (for multi-valued headers). If
       ``None`` is passed as value, the HTTP header will not be sent at all.
    :type headers: dict

    :param cookies: the request cookies. These can be sent in two forms.

        1. Using a dict::

            request_with_cookies = Request(url="http://www.example.com",
                                           cookies={'currency': 'USD', 'country': 'UY'})
        2. Using a list of dicts::

            request_with_cookies = Request(url="http://www.example.com",
                                           cookies=[{'name': 'currency',
                                                    'value': 'USD',
                                                    'domain': 'example.com',
                                                    'path': '/currency'}])

        The latter form allows for customizing the ``domain`` and ``path``
        attributes of the cookie. This is only useful if the cookies are saved
        for later requests.

        When some site returns cookies (in a response) those are stored in the
        cookies for that domain and will be sent again in future requests. That's
        the typical behaviour of any regular web browser. However, if, for some
        reason, you want to avoid merging with existing cookies you can instruct
        Scrapy to do so by setting the ``dont_merge_cookies`` key to True in the
        :attr:`Request.meta`.

        Example of request without merging cookies::

            request_with_cookies = Request(url="http://www.example.com",
                                           cookies={'currency': 'USD', 'country': 'UY'},
                                           meta={'dont_merge_cookies': True})

        For more info see :ref:`cookies-mw`.
    :type cookies: dict or list

    :param encoding: the encoding of this request (defaults to ``'utf-8'``).
       This encoding will be used to percent-encode the URL and to convert the
       body to ``str`` (if given as ``unicode``).
    :type encoding: string

    :param priority: the priority of this request (defaults to ``0``).
       The priority is used by the scheduler to define the order used to process
       requests.  Requests with a higher priority value will execute earlier.
       Negative values are allowed in order to indicate relatively low-priority.
    :type priority: int

    :param dont_filter: indicates that this request should not be filtered by
       the scheduler. This is used when you want to perform an identical
       request multiple times, to ignore the duplicates filter. Use it with
       care, or you will get into crawling loops. Default to ``False``.
    :type dont_filter: boolean

    :param errback: a function that will be called if any exception was
       raised while processing the request. This includes pages that failed
       with 404 HTTP errors and such. It receives a `Twisted Failure`_ instance
       as first parameter.
    :type errback: callable

    .. attribute:: Request.url

        A string containing the URL of this request. Keep in mind that this
        attribute contains the escaped URL, so it can differ from the URL passed in
        the constructor.

        This attribute is read-only. To change the URL of a Request use
        :meth:`replace`.

    .. attribute:: Request.method

        A string representing the HTTP method in the request. This is guaranteed to
        be uppercase. Example: ``"GET"``, ``"POST"``, ``"PUT"``, etc

    .. attribute:: Request.headers

        A dictionary-like object which contains the request headers.

    .. attribute:: Request.body

        A str that contains the request body.

        This attribute is read-only. To change the body of a Request use
        :meth:`replace`.

    .. attribute:: Request.meta

        A dict that contains arbitrary metadata for this request. This dict is
        empty for new Requests, and is usually  populated by different Scrapy
        components (extensions, middlewares, etc). So the data contained in this
        dict depends on the extensions you have enabled.

        See :ref:`topics-request-meta` for a list of special meta keys
        recognized by Scrapy.

        This dict is `shallow copied`_ when the request is cloned using the
        ``copy()`` or ``replace()`` methods, and can also be accessed, in your
        spider, from the ``response.meta`` attribute.

    .. _shallow copied: http://docs.python.org/library/copy.html

    .. method:: Request.copy()

       Return a new Request which is a copy of this Request. See also:
       :ref:`topics-request-response-ref-request-callback-arguments`.

    .. method:: Request.replace([url, method, headers, body, cookies, meta, encoding, dont_filter, callback, errback])

       Return a Request object with the same members, except for those members
       given new values by whichever keyword arguments are specified. The
       attribute :attr:`Request.meta` is copied by default (unless a new value
       is given in the ``meta`` argument). See also
       :ref:`topics-request-response-ref-request-callback-arguments`.

.. _topics-request-response-ref-request-callback-arguments:

Passing additional data to callback functions
---------------------------------------------

The callback of a request is a function that will be called when the response
of that request is downloaded. The callback function will be called with the
downloaded :class:`Response` object as its first argument.

Example::

    def parse_page1(self, response):
        return scrapy.Request("http://www.example.com/some_page.html",
                              callback=self.parse_page2)

    def parse_page2(self, response):
        # this would log http://www.example.com/some_page.html
        self.log("Visited %s" % response.url)

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
        return request

    def parse_page2(self, response):
        item = response.meta['item']
        item['other_url'] = response.url
        return item

.. _topics-request-meta:

Request.meta special keys
=========================

The :attr:`Request.meta` attribute can contain any arbitrary data, but there
are some special keys recognized by Scrapy and its built-in extensions.

Those are:

* :reqmeta:`dont_redirect`
* :reqmeta:`dont_retry`
* :reqmeta:`handle_httpstatus_list`
* ``dont_merge_cookies`` (see ``cookies`` parameter of :class:`Request` constructor)
* :reqmeta:`cookiejar`
* :reqmeta:`redirect_urls`
* :reqmeta:`bindaddress`
* :reqmeta:`dont_obey_robotstxt`
* :reqmeta:`download_timeout`

.. reqmeta:: bindaddress

bindaddress
-----------

The IP of the outgoing IP address to use for the performing the request.

.. reqmeta:: download_timeout

download_timeout
----------------

The amount of time (in secs) that the downloader will wait before timing out.
See also: :setting:`DOWNLOAD_TIMEOUT`.


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

.. _lxml.html forms: http://lxml.de/lxmlhtml.html#forms

.. class:: FormRequest(url, [formdata, ...])

    The :class:`FormRequest` class adds a new argument to the constructor. The
    remaining arguments are the same as for the :class:`Request` class and are
    not documented here.

    :param formdata: is a dictionary (or iterable of (key, value) tuples)
       containing HTML Form data which will be url-encoded and assigned to the
       body of the request.
    :type formdata: dict or iterable of tuples

    The :class:`FormRequest` objects support the following class method in
    addition to the standard :class:`Request` methods:

    .. classmethod:: FormRequest.from_response(response, [formname=None, formnumber=0, formdata=None, formxpath=None, clickdata=None, dont_click=False, ...])

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

       :param response: the response containing a HTML form which will be used
          to pre-populate the form fields
       :type response: :class:`Response` object

       :param formname: if given, the form with name attribute set to this value will be used.
       :type formname: string

       :param formxpath: if given, the first form that matches the xpath will be used.
       :type formxpath: string

       :param formnumber: the number of form to use, when the response contains
          multiple forms. The first one (and also the default) is ``0``.
       :type formnumber: integer

       :param formdata: fields to override in the form data. If a field was
          already present in the response ``<form>`` element, its value is
          overridden by the one passed in this parameter.
       :type formdata: dict

       :param clickdata: attributes to lookup the control clicked. If it's not
         given, the form data will be submitted simulating a click on the
         first clickable element. In addition to html attributes, the control
         can be identified by its zero-based index relative to other
         submittable inputs inside the form, via the ``nr`` attribute.
       :type clickdata: dict

       :param dont_click: If True, the form data will be submitted without
         clicking in any element.
       :type dont_click: boolean

       The other parameters of this class method are passed directly to the
       :class:`FormRequest` constructor.

       .. versionadded:: 0.10.3
          The ``formname`` parameter.

       .. versionadded:: 0.17
          The ``formxpath`` parameter.

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
                self.log("Login failed", level=log.ERROR)
                return

            # continue scraping with authenticated session...


Response objects
================

.. class:: Response(url, [status=200, headers, body, flags])

    A :class:`Response` object represents an HTTP response, which is usually
    downloaded (by the Downloader) and fed to the Spiders for processing.

    :param url: the URL of this response
    :type url: string

    :param headers: the headers of this response. The dict values can be strings
       (for single valued headers) or lists (for multi-valued headers).
    :type headers: dict

    :param status: the HTTP status of the response. Defaults to ``200``.
    :type status: integer

    :param body: the response body. It must be str, not unicode, unless you're
       using a encoding-aware :ref:`Response subclass
       <topics-request-response-ref-response-subclasses>`, such as
       :class:`TextResponse`.
    :type body: str

    :param meta: the initial values for the :attr:`Response.meta` attribute. If
       given, the dict will be shallow copied.
    :type meta: dict

    :param flags: is a list containing the initial values for the
       :attr:`Response.flags` attribute. If given, the list will be shallow
       copied.
    :type flags: list

    .. attribute:: Response.url

        A string containing the URL of the response.

        This attribute is read-only. To change the URL of a Response use
        :meth:`replace`.

    .. attribute:: Response.status

        An integer representing the HTTP status of the response. Example: ``200``,
        ``404``.

    .. attribute:: Response.headers

        A dictionary-like object which contains the response headers.

    .. attribute:: Response.body

        A str containing the body of this Response. Keep in mind that Response.body
        is always a str. If you want the unicode version use
        :meth:`TextResponse.body_as_unicode` (only available in
        :class:`TextResponse` and subclasses).

        This attribute is read-only. To change the body of a Response use
        :meth:`replace`.

    .. attribute:: Response.request

        The :class:`Request` object that generated this response. This attribute is
        assigned in the Scrapy engine, after the response and the request have passed
        through all :ref:`Downloader Middlewares <topics-downloader-middleware>`.
        In particular, this means that:

        - HTTP redirections will cause the original request (to the URL before
          redirection) to be assigned to the redirected response (with the final
          URL after redirection).

        - Response.request.url doesn't always equal Response.url

        - This attribute is only available in the spider code, and in the
          :ref:`Spider Middlewares <topics-spider-middleware>`, but not in
          Downloader Middlewares (although you have the Request available there by
          other means) and handlers of the :signal:`response_downloaded` signal.

    .. attribute:: Response.meta

        A shortcut to the :attr:`Request.meta` attribute of the
        :attr:`Response.request` object (ie. ``self.request.meta``).

        Unlike the :attr:`Response.request` attribute, the :attr:`Response.meta`
        attribute is propagated along redirects and retries, so you will get
        the original :attr:`Request.meta` sent from your spider.

        .. seealso:: :attr:`Request.meta` attribute

    .. attribute:: Response.flags

        A list that contains flags for this response. Flags are labels used for
        tagging Responses. For example: `'cached'`, `'redirected`', etc. And
        they're shown on the string representation of the Response (`__str__`
        method) which is used by the engine for logging.

    .. method:: Response.copy()

       Returns a new Response which is a copy of this Response.

    .. method:: Response.replace([url, status, headers, body, request, flags, cls])

       Returns a Response object with the same members, except for those members
       given new values by whichever keyword arguments are specified. The
       attribute :attr:`Response.meta` is copied by default.

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

    :class:`TextResponse` objects support a new constructor argument, in
    addition to the base :class:`Response` objects. The remaining functionality
    is the same as for the :class:`Response` class and is not documented here.

    :param encoding: is a string which contains the encoding to use for this
       response. If you create a :class:`TextResponse` object with a unicode
       body, it will be encoded using this encoding (remember the body attribute
       is always a string). If ``encoding`` is ``None`` (default value), the
       encoding will be looked up in the response headers and body instead.
    :type encoding: string

    :class:`TextResponse` objects support the following attributes in addition
    to the standard :class:`Response` ones:

    .. attribute:: TextResponse.encoding

       A string with the encoding of this response. The encoding is resolved by
       trying the following mechanisms, in order:

       1. the encoding passed in the constructor `encoding` argument

       2. the encoding declared in the Content-Type HTTP header. If this
          encoding is not valid (ie. unknown), it is ignored and the next
          resolution mechanism is tried.

       3. the encoding declared in the response body. The TextResponse class
          doesn't provide any special functionality for this. However, the
          :class:`HtmlResponse` and :class:`XmlResponse` classes do.

       4. the encoding inferred by looking at the response body. This is the more
          fragile method but also the last one tried.

    .. attribute:: TextResponse.selector

        A :class:`~scrapy.selector.Selector` instance using the response as
        target. The selector is lazily instantiated on first access.

    :class:`TextResponse` objects support the following methods in addition to
    the standard :class:`Response` ones:

    .. method:: TextResponse.body_as_unicode()

        Returns the body of the response as unicode. This is equivalent to::

            response.body.decode(response.encoding)

        But **not** equivalent to::

            unicode(response.body)

        Since, in the latter case, you would be using the system default encoding
        (typically `ascii`) to convert the body to unicode, instead of the response
        encoding.

    .. method:: TextResponse.xpath(query)

        A shortcut to ``TextResponse.selector.xpath(query)``::

            response.xpath('//p')

    .. method:: TextResponse.css(query)

        A shortcut to ``TextResponse.selector.css(query)``::

            response.css('p')


HtmlResponse objects
--------------------

.. class:: HtmlResponse(url[, ...])

    The :class:`HtmlResponse` class is a subclass of :class:`TextResponse`
    which adds encoding auto-discovering support by looking into the HTML `meta
    http-equiv`_ attribute.  See :attr:`TextResponse.encoding`.

.. _meta http-equiv: http://www.w3schools.com/TAGS/att_meta_http_equiv.asp

XmlResponse objects
-------------------

.. class:: XmlResponse(url[, ...])

    The :class:`XmlResponse` class is a subclass of :class:`TextResponse` which
    adds encoding auto-discovering support by looking into the XML declaration
    line.  See :attr:`TextResponse.encoding`.

.. _Twisted Failure: http://twistedmatrix.com/documents/current/api/twisted.python.failure.Failure.html

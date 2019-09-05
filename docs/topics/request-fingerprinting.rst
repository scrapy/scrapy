.. _request-fingerprinting:

======================
Request fingerprinting
======================

Request fingerprinting is the mechanism of calculating the *fingerprint* of a
request: a short array of :class:`bytes` that is expected to uniquely identify
that request. The fingerprint of a request can be used for tasks like ignoring
duplicate requests (see :setting:`DUPEFILTER_CLASS`) or handling response
caches (see
:class:`~scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware`).

You often don’t need to worry about request fingerprinting, the default request
fingerprinting of Scrapy works for most projects. It takes into account a
canonical version (:func:`w3lib.url.canonicalize_url`) of
:attr:`request.url <scrapy.http.Request.url>` and the values of
:attr:`request.method <scrapy.http.Request.method>` and
:attr:`request.body <scrapy.http.Request.body>`.

Continue reading to learn how to change request fingerprinting, for example to
take into account some headers or compare URLs case-insensitively.

.. _configuring_request_fingerprinting:

Configuring request fingerprinting
==================================

The process of generating a request fingerprint is split in three steps, all of
which can be overriden through settings or their corresponding
:attr:`request.meta <scrapy.http.Request.meta>` keys:

1.  Select a subset of the request data that uniquely identifies the request
    (:setting:`REQUEST_FINGERPRINT_PROCESSORS`)

2.  Turn that subset of data into an equivalent byte string
    (:setting:`REQUEST_FINGERPRINT_SERIALIZER`)

3.  Generate a hash of that request-identifying byte string
    (:setting:`REQUEST_FINGERPRINT_HASHER`)

.. setting:: REQUEST_FINGERPRINT_PROCESSORS
.. reqmeta:: fingerprint_processors

REQUEST_FINGERPRINT_PROCESSORS
------------------------------

Default: ``[scrapy.utils.request.process_request_fingerprint]``

Equivalent :attr:`Request.meta <scrapy.http.Request.meta>` key:
``fingerprint_processors``

A list of methods that receive two possitional parameters, ``request`` and
``data`` (a :class:`dict`, empty unless filled by a previous processor), and
must return a dictionary containing the data that must be used to generate a
fingerprint for the target :class:`request <scrapy.http.Request>`.

These methods are executed in a loop, in the provided order. They may add,
modify or remove data from the input :class:`dict`.

Most use cases can be covered by combining Python’s :func:`~functools.partial`
with Scrapy’s :func:`~scrapy.utils.request.process_request_fingerprint`:

.. autofunction:: scrapy.utils.request.process_request_fingerprint

.. note:: There is technically no restriction on the type of data that each
          :class:`dict` key may contain. In fact, it is technically possible to
          return something other than a :class:`dict` if other request
          fingerprinting settings are modified accordingly.


.. setting:: REQUEST_FINGERPRINT_SERIALIZER
.. reqmeta:: fingerprint_serializer

REQUEST_FINGERPRINT_SERIALIZER
------------------------------

Default: ``scrapy.utils.request.json_serializer``

Equivalent :attr:`Request.meta <scrapy.http.Request.meta>` key:
``fingerprint_serializer``

A method that received a :class:`dict` and serializer it into a :class:`bytes`
representation of its data.

The default value is :func:`~scrapy.utils.request.json_serializer`:

.. autofunction:: scrapy.utils.request.json_serializer


.. setting:: REQUEST_FINGERPRINT_HASHER
.. reqmeta:: fingerprint_hasher

REQUEST_FINGERPRINT_HASHER
--------------------------

Default: ``scrapy.utils.request.sha1_hasher``

Equivalent :attr:`Request.meta <scrapy.http.Request.meta>` key:
``fingerprint_hasher``

A method that received a :class:`dict` and serializer it into a :class:`bytes`
representation of its data.

The default value is :func:`~scrapy.utils.request.sha1_hasher`:

.. autofunction:: scrapy.utils.request.sha1_hasher


Request fingerprinting recipes
==============================

The following sections are recipes of ways to :ref:`configure request
fingerprinting <configuring_request_fingerprinting>` to get certain behaviors.

Include some headers
--------------------

::

    from functools import partial
    from scrapy.utils.request import process_request_fingerprint

    REQUEST_FINGERPRINT_PROCESSORS = [
        partial(process_request_fingerprint, headers={'X-My-Header'}),
    ]


Compare URLs case-insensitively
-------------------------------

::

    from functools import partial
    from w3lib.url import canonicalize_url
    from scrapy.utils.request import process_request_fingerprint

    def url_processor(url):
        return canonicalize_url(url).lower()

    REQUEST_FINGERPRINT_PROCESSORS = [
        partial(process_request_fingerprint, url_processor=url_processor),
    ]


Ignore some query string parameters
-----------------------------------

::

    from functools import partial
    from w3lib.url import canonicalize_url, url_query_cleaner
    from scrapy.utils.request import process_request_fingerprint

    def url_processor(url):
        url = canonicalize_url(url)
        parameters = ['parameters', 'to', 'ignore']
        return url_query_cleaner(url, parameterlist=parameters, remove=True)

    REQUEST_FINGERPRINT_PROCESSORS = [
        partial(process_request_fingerprint, url_processor=url_processor),
    ]


Reproduce pre-VERSION fingerprints
----------------------------------

It’s possible to reproduce request fingerprints identical to those that used to
be generated before Scrapy VERSION::

    import hashlib
    from w3lib.url import canonicalize_url
    from scrapy.utils.python import to_bytes

    def old_serializer(request):
        method = to_bytes(request.method)
        url = to_bytes(canonicalize_url(request.url))
        body = request.body or b''
        return method + url + body

    REQUEST_FINGERPRINT_PROCESSORS = [lambda x, y: x]
    REQUEST_FINGERPRINT_SERIALIZER = old_serializer
    REQUEST_FINGERPRINT_HASHER = lambda x: hashlib.sha1(x).hexdigest()



Using request fingerprints
==========================

Code that needs the fingerprint of a request must use
:func:`scrapy.utils.request.request_fingerprint` to read it:

.. autofunction:: scrapy.utils.request.request_fingerprint


.. _override-request-fingerprinting:

Overriding the fingerprint of a request
=======================================

It’s technically possible to override how request fingerprints are calculated
by manually defining the fingerprint of a request::

    request.fingerprint = b'custom fingerprint'

If :attr:`request.fingerprint <scrapy.http.Request.fingerprint>` has a
value, it overrides request fingerprinting. This approach, however, has some
drawbacks:

-   It overrides all request fingerprinting settings.

-   If done at a point where ``request.fingerprint`` already has a value, it
    usually means that the previous fingerprint has already been used by one or
    more Scrapy components that will not take the new value into account.

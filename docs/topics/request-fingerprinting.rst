.. _request-fingerprinting:

======================
Request fingerprinting
======================

Request fingerprinting is the mechanism of calculating the *fingerprint* of a
request: a short array of :class:`bytes`, a *hash*, that is *likely* to
uniquely identify that request. The fingerprint of a request can be used for
tasks like ignoring duplicate requests (see :setting:`DUPEFILTER_CLASS`) or
handling response caches (see
:class:`~scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware`).

You often don’t need to worry about request fingerprinting, the default request
fingerprinting of Scrapy works for most projects. It takes into account a
canonical version (:func:`w3lib.url.canonicalize_url`) of
:attr:`request.url <scrapy.http.Request.url>` and the values of
:attr:`request.method <scrapy.http.Request.method>` and
:attr:`request.body <scrapy.http.Request.body>`.

Continue reading to learn how to change request fingerprinting, for example to
take into account some headers or compare URLs case-insensitively.

Overriding the fingerprint of a request
=======================================

One way to override how request fingerprints are calculated is to manually
define the fingerprint of a request::

    request.fingerprint = b'custom fingerprint'

If :att:`request.fingerprint <scrapy.http.request.Request.fingerprint>` has a
value, it overrides global request fingerprinting.

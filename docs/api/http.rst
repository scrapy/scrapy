========
HTTP API
========

Requests
========

.. autoclass:: scrapy.Request
    :members:

.. autoclass:: scrapy.FormRequest
    :members:

.. autoclass:: scrapy.http.XmlRpcRequest
   :members:


Responses
=========

.. autoclass:: scrapy.http.Response
    :members:

.. autoclass:: scrapy.http.TextResponse
    :members:

.. autoclass:: scrapy.http.HtmlResponse
    :members:

.. autoclass:: scrapy.http.XmlResponse


Headers
=======

.. automodule:: scrapy.http.headers
    :members:
    :exclude-members: Headers

.. autoclass:: scrapy.http.Headers
    :members:


Cookies
=======

.. automodule:: scrapy.http.cookies
   :members:


.. _bug in lxml: https://bugs.launchpad.net/lxml/+bug/1665241
.. _Twisted Failure: https://twistedmatrix.com/documents/current/api/twisted.python.failure.Failure.html
.. _urlparse.urljoin: https://docs.python.org/2/library/urlparse.html#urlparse.urljoin

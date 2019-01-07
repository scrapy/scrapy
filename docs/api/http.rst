========
HTTP API
========

Requests
========

.. class:: scrapy.http.request.Request
.. class:: scrapy.http.Request
.. autoclass:: scrapy.Request
   :members:

.. class:: scrapy.http.request.form.FormRequest
.. class:: scrapy.http.FormRequest
.. autoclass:: scrapy.FormRequest
   :members:

.. class:: scrapy.http.request.rpc.XmlRpcRequest
.. autoclass:: scrapy.http.XmlRpcRequest
   :members:


Responses
=========

.. class:: scrapy.http.response.Response
.. autoclass:: scrapy.http.Response
   :members:

.. class:: scrapy.http.response.text.TextResponse
.. autoclass:: scrapy.http.TextResponse
   :members:

.. class:: scrapy.http.response.html.HtmlResponse
.. autoclass:: scrapy.http.HtmlResponse
   :members:

.. class:: scrapy.http.response.xml.XmlResponse
.. autoclass:: scrapy.http.XmlResponse
   :members:


Headers
=======

.. automodule:: scrapy.http.headers
   :members:
   :exclude-members: Headers

.. class:: scrapy.http.headers.Headers
.. autoclass:: scrapy.http.Headers
   :members:
   :inherited-members:
   :undoc-members:


Cookies
=======

.. automodule:: scrapy.http.cookies
   :members:


.. _bug in lxml: https://bugs.launchpad.net/lxml/+bug/1665241
.. _Twisted Failure: https://twistedmatrix.com/documents/current/api/twisted.python.failure.Failure.html
.. _urlparse.urljoin: https://docs.python.org/2/library/urlparse.html#urlparse.urljoin

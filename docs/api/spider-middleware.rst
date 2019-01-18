=====================
Spider Middleware API
=====================

.. _topics-spider-middleware-ref:

Built-in spider middlewares
===========================

.. note:: For a list of the components enabled by default (and their orders)
          see the :setting:`SPIDER_MIDDLEWARES_BASE` setting.

DepthMiddleware
---------------

.. autoclass:: scrapy.spidermiddlewares.depth.DepthMiddleware


HttpErrorMiddleware
-------------------

.. autoclass:: scrapy.spidermiddlewares.httperror.HttpErrorMiddleware


OffsiteMiddleware
-----------------

.. autoclass:: scrapy.spidermiddlewares.offsite.OffsiteMiddleware


RefererMiddleware
-----------------

.. currentmodule:: scrapy.spidermiddlewares.referer

.. autoclass:: RefererMiddleware

.. autoclass:: DefaultReferrerPolicy

.. autoclass:: NoReferrerPolicy

.. autoclass:: NoReferrerWhenDowngradePolicy

.. autoclass:: SameOriginPolicy

.. autoclass:: OriginPolicy

.. autoclass:: StrictOriginPolicy

.. autoclass:: OriginWhenCrossOriginPolicy

.. autoclass:: StrictOriginWhenCrossOriginPolicy

.. autoclass:: UnsafeUrlPolicy

.. _Referrer Policy: https://www.w3.org/TR/referrer-policy
.. _"no-referrer": https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer
.. _"no-referrer-when-downgrade": https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer-when-downgrade
.. _"same-origin": https://www.w3.org/TR/referrer-policy/#referrer-policy-same-origin
.. _"origin": https://www.w3.org/TR/referrer-policy/#referrer-policy-origin
.. _"strict-origin": https://www.w3.org/TR/referrer-policy/#referrer-policy-strict-origin
.. _"origin-when-cross-origin": https://www.w3.org/TR/referrer-policy/#referrer-policy-origin-when-cross-origin
.. _"strict-origin-when-cross-origin": https://www.w3.org/TR/referrer-policy/#referrer-policy-strict-origin-when-cross-origin
.. _"unsafe-url": https://www.w3.org/TR/referrer-policy/#referrer-policy-unsafe-url


UrlLengthMiddleware
-------------------

.. autoclass:: scrapy.spidermiddlewares.urllength.UrlLengthMiddleware


Spider middleware interface
===========================

.. autointerface:: scrapy.interfaces.ISpiderMiddleware
   :members:


Spider middleware manager
=========================

.. autoclass:: scrapy.middleware.MiddlewareManager
   :members:

.. _topics-webservice:

===========
Web Service
===========

Scrapy comes with a built-in web service for monitoring and controlling a
running crawler. The service exposes most resources using the `JSON-RPC 2.0`_
protocol, but there are also other (read-only) resources which just output JSON
data.

Provides an extensible web service for managing a Scrapy process. It's enabled
by the :setting:`WEBSERVICE_ENABLED` setting. The web server will listen in the
port specified in :setting:`WEBSERVICE_PORT`, and will log to the file
specified in :setting:`WEBSERVICE_LOGFILE`.

The web service is a :ref:`built-in Scrapy extension <topics-extensions-ref>`
which comes enabled by default, but you can also disable it if you're running
tight on memory.

.. _topics-webservice-resources:

Web service resources
=====================

The web service contains several resources, defined in the
:setting:`WEBSERVICE_RESOURCES` setting. Each resource provides a different
functionality. See :ref:`topics-webservice-resources-ref` for a list of
resources available by default.

Althought you can implement your own resources using any protocol, there are
two kinds of resources bundled with Scrapy:

* Simple JSON resources - which are read-only and just output JSON data
* JSON-RPC resources - which provide direct access to certain Scrapy objects
  using the `JSON-RPC 2.0`_ protocol

.. module:: scrapy.contrib.webservice
   :synopsis: Built-in web service resources

.. _topics-webservice-resources-ref:

Available JSON-RPC resources
----------------------------

These are the JSON-RPC resources available by default in Scrapy:

.. _topics-webservice-crawler:

Crawler JSON-RPC resource
~~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.webservice.crawler
   :synopsis: Crawler JSON-RPC resource

.. class:: CrawlerResource

    Provides access to the main Crawler object that controls the Scrapy
    process.

    Available by default at: http://localhost:6080/crawler

Stats Collector JSON-RPC resource
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.webservice.stats
   :synopsis: Stats JSON-RPC resource

.. class:: StatsResource

    Provides access to the Stats Collector used by the crawler.

    Available by default at: http://localhost:6080/stats

Spider Manager JSON-RPC resource
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can access the spider manager JSON-RPC resource through the
:ref:`topics-webservice-crawler` at: http://localhost:6080/crawler/spiders

Extension Manager JSON-RPC resource
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can access the extension manager JSON-RPC resource through the
:ref:`topics-webservice-crawler` at: http://localhost:6080/crawler/spiders

Available JSON resources
------------------------

These are the JSON resources available by default:

Engine status JSON resource
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.webservice.enginestatus
   :synopsis: Engine Status JSON resource

.. class:: EngineStatusResource

    Provides access to engine status metrics.

    Available by default at: http://localhost:6080/enginestatus

Web service settings
====================

These are the settings that control the web service behaviour:

.. setting:: WEBSERVICE_ENABLED

WEBSERVICE_ENABLED
------------------

Default: ``True``

A boolean which specifies if the web service will be enabled (provided its
extension is also enabled).

.. setting:: WEBSERVICE_LOGFILE

WEBSERVICE_LOGFILE
------------------

Default: ``None``

A file to use for logging HTTP requests made to the web service. If unset web
the log is sent to standard scrapy log.

.. setting:: WEBSERVICE_PORT

WEBSERVICE_PORT
---------------

Default: ``[6080, 7030]``

The port range to use for the web service. If set to ``None`` or ``0``, a
dynamically assigned port is used.

.. setting:: WEBSERVICE_HOST

WEBSERVICE_HOST
---------------

Default: ``'0.0.0.0'``

The interface the web service should listen on

WEBSERVICE_RESOURCES
--------------------

Default: ``{}``

The list of web service resources enabled for your project. See
:ref:`topics-webservice-resources`. These are added to the ones available by
default in Scrapy, defined in the :setting:`WEBSERVICE_RESOURCES_BASE` setting.

WEBSERVICE_RESOURCES_BASE
-------------------------

Default::

    {
        'scrapy.contrib.webservice.crawler.CrawlerResource': 1,
        'scrapy.contrib.webservice.enginestatus.EngineStatusResource': 1,
        'scrapy.contrib.webservice.stats.StatsResource': 1,
    }

The list of web service resources available by default in Scrapy. You shouldn't
change this setting in your project, change :setting:`WEBSERVICE_RESOURCES`
instead. If you want to disable some resource set its value to ``None`` in
:setting:`WEBSERVICE_RESOURCES`.

Writing a web service resource
==============================

Web service resources are implemented using the Twisted Web API. See this
`Twisted Web guide`_ for more information on Twisted web and Twisted web
resources.

To write a web service resource you should subclass the :class:`JsonResource` or
:class:`JsonRpcResource` classes and implement the :class:`renderGET` method. 

.. class:: scrapy.webservice.JsonResource

    A subclass of `twisted.web.resource.Resource`_ that implements a JSON web
    service resource. See 

    .. attribute:: ws_name

        The name by which the Scrapy web service will known this resource, and
        also the path wehere this resource will listen. For example, assuming
        Scrapy web service is listening on http://localhost:6080/ and the
        ``ws_name`` is ``'resource1'`` the URL for that resource will be:

            http://localhost:6080/resource1/

.. class:: scrapy.webservice.JsonRpcResource(crawler, target=None)

    This is a subclass of :class:`JsonResource` for implementing JSON-RPC
    resources. JSON-RPC resources wrap Python (Scrapy) objects around a
    JSON-RPC API. The resource wrapped must be returned by the
    :meth:`get_target` method, which returns the target passed in the
    constructor by default

    .. method:: get_target()
        
        Return the object wrapped by this JSON-RPC resource. By default, it
        returns the object passed on the constructor.

Examples of web service resources
=================================

StatsResource (JSON-RPC resource)
---------------------------------

.. literalinclude:: ../../scrapy/contrib/webservice/stats.py

EngineStatusResource (JSON resource)
-------------------------------------

.. literalinclude:: ../../scrapy/contrib/webservice/enginestatus.py

Example of web service client
=============================

scrapy-ws.py script
-------------------

.. literalinclude:: ../../extras/scrapy-ws.py

.. _Twisted Web guide: http://jcalderone.livejournal.com/50562.html 
.. _JSON-RPC 2.0: http://www.jsonrpc.org/
.. _twisted.web.resource.Resource: http://twistedmatrix.com/documents/10.0.0/api/twisted.web.resource.Resource.html 


.. _topics-extensions:

==========
Extensions
==========

The extensions framework provide a mechanism for inserting your own
custom functionality into Scrapy. 

Extensions are just regular classes that are instantiated at Scrapy startup,
when extensions are initialized.

Extension settings
==================

Extensions use the :ref:`Scrapy settings <topics-settings>` to manage their
settings, just like any other Scrapy code.

It is customary for extensions to prefix their settings with their own name, to
avoid collision with existing (and future) extensions. For example, an
hypothetic extension to handle `Google Sitemaps`_ would use settings like
`GOOGLESITEMAP_ENABLED`, `GOOGLESITEMAP_DEPTH`, and so on.

.. _Google Sitemaps: http://en.wikipedia.org/wiki/Sitemaps

Loading & activating extensions
===============================

Extensions are loaded and activated at startup by instantiating a single
instance of the extension class. Therefore, all the extension initialization
code must be performed in the class constructor (``__init__`` method).

To make an extension available, add it to the :setting:`EXTENSIONS` setting in
your Scrapy settings. In :setting:`EXTENSIONS`, each extension is represented
by a string: the full Python path to the extension's class name. For example::

    EXTENSIONS = {
        'scrapy.stats.corestats.CoreStats': 500,
        'scrapy.management.web.WebConsole': 500,
        'scrapy.management.telnet.TelnetConsole': 500,
        'scrapy.contrib.webconsole.enginestatus.EngineStatus': 500,
        'scrapy.contrib.webconsole.stats.StatsDump': 500,
        'scrapy.contrib.debug.StackTraceDump': 500,
    }


As you can see, the :setting:`EXTENSIONS` setting is a dict where the keys are
the extension paths, and their values are the orders, which define the
extension *loading* order. Extensions orders are not as important as middleware
orders though, and they are typically irrelevant, ie. it doesn't matter in
which order the extensions are loaded because they don't depend on each other
[1].

However this feature can be exploited if you need to add an extension which
depends on other extension already loaded.

[1] This is is why the :setting:`EXTENSIONS_BASE` setting in Scrapy (which
contains all built-in extensions enabled by default) defines all the extensions
with the same order (``500``).

Available, enabled and disabled extensions
==========================================

Not all available extensions will be enabled. Some of them usually depend on a
particular setting. For example, the HTTP Cache extension is available by default
but disabled unless the :setting:`HTTPCACHE_DIR` setting is set.  Both enabled
and disabled extension can be accessed through the
:ref:`ref-extension-manager`.

Accessing enabled extensions
============================

Even though it's not usually needed, you can access extension objects through
the :ref:`ref-extension-manager` which is populated when extensions are loaded.
For example, to access the ``WebConsole`` extension::

    from scrapy.extension import extensions
    webconsole_extension = extensions.enabled['WebConsole']

.. seealso::

    :ref:`ref-extension-manager`, for the complete Extension manager reference.

Writing your own extension
==========================

Writing your own extension is easy. Each extension is a single Python class
which doesn't need to implement any particular method. 

All extension initialization code must be performed in the class constructor
(``__init__`` method). If that method raises the :exception:`NotConfigured`
exception, the extension will be disabled. Otherwise, the extension will be
enabled.

Let's take a look at the following example extension which just logs a message
everytime a domain/spider is opened and closed::

    from scrapy.xlib.pydispatch import dispatcher
    from scrapy.core import signals

    class SpiderOpenCloseLogging(object):

        def __init__(self):
            dispatcher.connect(self.domain_opened, signal=signals.domain_opened)
            dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

        def domain_opened(self, domain, spider):
            log.msg("opened domain %s" % domain)

        def domain_closed(self, domain, spider):
            log.msg("closed domain %s" % domain)

Built-in extensions
===================

See :ref:`ref-extensions`.


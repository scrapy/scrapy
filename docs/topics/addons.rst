.. _topics-addons:

=======
Add-ons
=======

Scrapy's add-on system is a framework which unifies managing and configuring
components that extend Scrapy's core functionality, such as middlewares,
extensions, or pipelines. It provides users with a plug-and-play experience in
Scrapy extension management, and grants extensive configuration control to
developers.


Activating and configuring add-ons
==================================

Add-ons and their configuration live in Scrapy's
:class:`~scrapy.addons.AddonManager`. During Scrapy's start-up process, and
only then, the add-on manager will read a list of enabled add-ons and their
configurations from your settings. There are two places where you can provide
the paths to add-ons you want to enable:

* the ``INSTALLED_ADDONS`` setting, and
* the ``scrapy.cfg`` file.

As Scrapy settings can be modified from many places, e.g. in a project's
``settings.py``, in a Spider's ``custom_settings`` attribute, or from the
command line, using the ``INSTALLED_ADDONS`` setting is the preferred way to
manage add-ons.

The ``INSTALLED_ADDONS`` setting a tuple in which every item is a path to an
add-on. The path can be both a Python or a file path. While more precise, it is
not necessary to specify the full add-on Python path if it is either built into
Scrapy or lives in your project's ``addons`` submodule.

The configuration of an add-on, if necessary at all, is stored as a dictionary
setting whose name is the uppercase add-on name.

This is an example where an internal add-on and two third-party add-ons (in this
case with one requiring no configuration) are enabled/configured in a project's
``settings.py``::

    INSTALLED_ADDONS = (
        'httpcache',
        'path.to.some.addon',
        'path/to/other/addon.py',
    )

    HTTPCACHE = {
        'expiration_secs': 60,
        'ignore_http_codes': [404, 405],
    }

    SOMEADDON = {
        'some_config': True,
    }

It is also possible to manage add-ons from ``scrapy.cfg``. While the syntax is
a little friendlier, be aware that this file, and therefore the configuration in
it, is not bound to a particular Scrapy project. While this should not pose a
problem when you use the project on your development machine only, a common
stumbling block is that ``scrapy.cfg`` is not deployed via ``scrapyd-deploy``.

In ``scrapy.cfg``, section names, prepended with ``addon:``, replace the
dictionary keys. I.e., the configuration from above would look like this:

.. code-block:: cfg

    [addon:httpcache]
    expiration_secs = 60
    ignore_http_codes = 404,405

    [addon:path.to.some.addon]
    some_config = true

    [addon:path/to/other/addon.py]


Enabling and configuring add-ons within Python code
---------------------------------------------------

The :class:`~scrapy.addons.AddonManager` will only read from Scrapy's settings
and from ``scrapy.cfg`` *at the beginning* of Scrapy's start-up process.
Afterwards, i.e. as soon as the :class:`~scrapy.addons.AddonManager` is
populated, changing the ``INSTALLED_ADDONS`` setting or any of the add-on
configuration dictionary settings will have no effect.

If you want to enable, disable, or configure add-ons in Python code, for example
when writing your own add-on, you will have to use the
:class:`~scrapy.addons.AddonManager`. You can access the add-on manager through
either ``crawler.addons`` or, if you are writing an add-on, through the
``addons`` argument of the :meth:`update_addons` callback. The add-on manager
provides many useful methods and attributes to facilitate interacting with the
add-ons framework, e.g.:

* an :meth:`~scrapy.addons.AddonManager.add` method to load add-ons,
* the :attr:`~scrapy.addons.AddonManager.enabled` list of enabled add-ons,
* :meth:`~scrapy.addons.AddonManager.enable` and
  :meth:`~scrapy.addons.AddonManager.disable` methods,
* the :attr:`~scrapy.addons.AddonManager.configs` dictionary which holds the
  configuration of all add-ons

In this example, we ensure that the ``httpcache`` add-on is loaded, and that
its ``expiration_secs`` configuration is set to ``60``::

    # addons is an instance of AddonManager
    if 'httpcache' not in addons:
        addons.add('httpcache', {'expiration_secs': 60})
    else:
        addons.configs['httpcache']['expiration_secs'] = 60


Writing your own add-ons
========================

Add-ons are (any) Python *objects* that provide Scrapy's *add-on interface*.
The interface is enforced through ``zope.interface``. This leaves the choice of
Python object up the developer. Examples:

* for a small pipeline, the add-on interface could be implemented in the same
  class that also implements the ``open/close_spider`` and ``process_item``
  callbacks
* for larger add-ons, or for clearer structure, the interface could be provided
  by a stand-alone module

The absolute minimum interface consists of two attributes:

.. attribute:: name

    string with add-on name

.. attribute:: version

    version string (PEP-404, e.g. ``'1.0.1'``)

Of course, stating just these two attributes will not get you very far. Add-ons
can provide three callback methods that are called at various stages before the
crawling process:

.. method:: update_settings(config, settings)

    This method is called during the initialization of the
    :class:`~scrapy.crawler.Crawler`. Here, you should perform dependency checks
    (e.g. for external Python libraries) and update the
    :class:`~scrapy.settings.Settings` object as wished, e.g. enable components
    for this add-on or set required configuration of other extensions.

    :param config: Configuration of this add-on
    :type config: ``dict``

    :param settings: The settings object storing Scrapy/component configuration
    :type settings: :class:`~scrapy.settings.Settings`

.. method:: check_configuration(config, crawler)

    This method is called when the :class:`~scrapy.crawler.Crawler` has been
    fully initialized, immediately before it starts crawling. You can perform
    additional dependency and configuration checks here.

    :param config: Configuration of this add-on
    :type config: ``dict``

    :param crawler: Fully initialized Scrapy crawler
    :type crawler: :class:`~scrapy.crawler.Crawler`

.. method:: update_addons(config, addons)

    This method is called immediately before :meth:`update_settings`, and should
    be used to enable and configure other *add-ons* only.

    When using this callback, be aware that there is no guarantee in which order
    the :meth:`update_addons` callbacks of enabled add-ons will be called.
    Add-ons that are added to the :class:`~scrapy.addons.AddonManager` during 
    this callback will also have their :meth:`update_addons` method called.

    :param config: Configuration of this add-on
    :type config: ``dict``

    :param addons: Add-on manager holding all loaded add-ons
    :type addons: :class:`~scrapy.addons.AddonManager`

Additionally, add-ons may (and should, where appropriate) provide one or more
attributes that can be used for limited automated detection of possible
dependency clashes:

.. attribute:: requires

    list of built-in or custom components needed by this add-on, as strings.

.. attribute:: modifies

    list of built-in or custom components whose functionality is affected or
    replaced by this add-on (a custom HTTP cache should list ``httpcache`` here)

.. attribute:: provides

    list of components provided by this add-on (e.g. ``mongodb`` for an
    extension that provides generic read/write access to a MongoDB database)

The entries in the :attr:`requires` and :attr:`modifies` attributes can be add-on
names or components from other add-ons' :attr:`provides` attribute. You can
specify :pep:`440`-style information about required versions. Examples::

    requires = ['httpcache']
    requires = ['otheraddon >= 2.0', 'yetanotheraddon']

The Python object or module that is pointed to by an add-on path (e.g. given in
the ``INSTALLED_ADDONS`` setting, or given to
:meth:`~scrapy.addons.AddonManager.add`) does not necessarily have to be an
add-on. Instead, it can provide an ``_addon`` attribute. This attribute can be
either an add-on or another add-on path.


Add-on base class
=================

Scrapy comes with a built-in base class for add-ons which provides some
convenience functionality:

* basic settings can be exported via :meth:`~scrapy.addons.Addon.export_basics`,
  configurable via :attr:`~scrapy.addons.Addon.basic_settings`.
* a single component (e.g. an item pipeline or a downloader middleware) can be
  inserted into Scrapy's settings via
  :meth:`~scrapy.addons.Addon.export_component`, configurable via
  :attr:`~scrapy.addons.Addon.component_type`,
  :attr:`~scrapy.addons.Addon.component_key`,
  :attr:`~scrapy.addons.Addon.component`, and the ``order`` key in
  :attr:`~scrapy.addons.Addon.default_config`.
* the add-on configuration can be exposed into Scrapy's settings via
  :meth:`~scrapy.addons.Addon.export_config`, configurable via
  :attr:`~scrapy.addons.Addon.default_config`,
  :attr:`~scrapy.addons.Addon.config_mapping`, and
  :attr:`~scrapy.addons.Addon.settings_prefix`.

By default, the base add-on class will expose the add-on configuration into
Scrapy's settings namespace, in caps and with the add-on name prepended. It is
easy to write your own functionality while still being able to use the
convenience functions by overwriting
:meth:`~scrapy.addons.Addon.update_settings`.

.. module:: scrapy.addons

.. autoclass:: Addon
   :members:


Add-on examples
===============

Set some basic configuration using the :class:`Addon` base class::

    from scrapy.addons import Addon

    class MyAddon(Addon):
        name = 'myaddon'
        version = '1.0'
        component = 'path.to.mypipeline'
        component_type = 'ITEM_PIPELINES'
        component_order = 200
        basic_settings = {
            'DNSCACHE_ENABLED': False,
        }

Check dependencies::

    from scrapy.addons import Addon

    class MyAddon(Addon):
        name = 'myaddon'
        version = '1.0'

        def update_settings(self, config, settings):
            try:
                import boto
            except ImportError:
                raise RuntimeError("myaddon requires the boto library")
            else:
                self.export_config(config, settings)

Enable a component that lives relative to the add-on (see
:ref:`topics-api-settings`)::

    from scrapy.addons import Addon

    class MyAddon(Addon):
        name = 'myaddon'
        version = '1.0'
        component = __name__ + '.downloadermw.coolmw'
        component_type = 'DOWNLOADER_MIDDLEWARES'
        component_order = 900

Instantiate components ad hoc::

    from path.to.my.pipelines import MySQLPipeline

    class MyAddon(object):
        name = 'myaddon'
        version = '1.0'

        def update_settings(self, config, settings):
            mysqlpl = MySQLPipeline(password=config['password'])
            settings.set(
                'ITEM_PIPELINES',
                {mysqlpl: 200},
                priority='addon',
            )

Provide add-on interface along component interface::

    class MyPipeline(object):
        name = 'mypipeline'
        version = '1.0'

        def process_item(self, item, spider):
            # Do some processing here
            return item

        def update_settings(self, config, settings):
            settings.set(
                'ITEM_PIPELINES',
                {self: 200},
                priority='addon',
            )

Enable another addon (see :ref:`topics-api-addonmanager`)::

    class MyAddon(object):
        name = 'myaddon'
        version = '1.0'

        def update_addons(self, config, addons):
            if 'httpcache' not in addons.enabled:
                addons.add('httpcache', {'expiration_secs': 60})

Check configuration of fully initialized crawler (see
:ref:`topics-api-crawler`)::

    class MyAddon(object):
        name = 'myaddon'
        version = '1.0'

        def update_settings(self, config, settings):
            settings.set('DNSCACHE_ENABLED', False, priority='addon')

        def check_configuration(self, config, crawler):
            if crawler.settings.getbool('DNSCACHE_ENABLED'):
                # The spider, some other add-on, or the user messed with the
                # DNS cache setting
                raise ValueError("myaddon is incompatible with DNS cache")

Provide add-on interface through a module:

.. No idea why just using '::' doesn't work for this one
.. code-block:: python

    name = 'AddonModule'
    version = '1.0'

    class MyPipeline(object):
        # ...

    class MyDownloaderMiddleware(object):
        # ...

    def update_settings(config, settings):
        settings.set(
            'ITEM_PIPELINES',
            {MyPipeline(): 200},
            priority='addon',
            }
        settings.set(
            'DOWNLOADER_MIDDLEWARES',
            {MyDownloaderMiddleware(): 800},
            priority='addon',
            }

Forward to other add-ons depending on Python version::

    # This could be a Python module, say project/pipelines/mypipeline.py, but
    # could also be done inside a class, etc.
    import six

    if six.PY3:
        # We're running Python 3
        _addon = 'path.to.addon'
    else:
        _addon = 'path.to.other.addon'


Built-in add-on reference
=========================

Scrapy comes with gateway add-ons that you can use to configure the built-in
middlewares and extensions. For example, to activate and configure the
:class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`, instead
of placing this in your ``settings.py``::

    HTTPCACHE_ENABLED = True
    HTTPCACHE_EXPIRATION_SECS = 60
    HTTPCACHE_IGNORE_HTTP_CODES = [404]

you can also use the add-on framework::

    INSTALLED_ADDONS = (
        # ...,
        'httpcache',
    )

    HTTPCACHE = {
        'expiration_secs': 60,
        'ignore_http_codes': [404],
        }

Note that you *must* enable built-in addons by placing them in your
``INSTALLED_ADDONS`` setting before you can use them for configuring built-in
components. I.e., configuring the ``HTTPCACHE`` setting will have no effect
when ``httpcache`` is not listed in ``INSTALLED_ADDONS``.

In general, the add-on names match the lowercase name of the component, with its
type suffix removed (i.e. the add-on configuring the
:class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware` is called
``httpcache``), and the configuration option names match the names of the
settings they map to, with the component prefix removed (i.e.
``expiration_secs`` maps to :setting:`HTTPCACHE_EXPIRATION_SECS`, as above).
The available add-ons are:


+--------------------------------------+--------------------------------------+
| Add-on                               | Notes                                |
+======================================+======================================+
| **Spider middlewares**                                                      |
+--------------------------------------+--------------------------------------+
| depth (:class:`~scrapy.spidermi\     |                                      |
| ddlewares.depth.DepthMiddleware`)    |                                      |
+--------------------------------------+--------------------------------------+
| httperror (:class:`~scrapy.spid\     |                                      |
| ermiddlewares.httperror.HttpErrorMi\ |                                      |
| ddleware`)                           |                                      |
+--------------------------------------+--------------------------------------+
| offsite (:class:`~scrapy.spid\       |                                      |
| ermiddlewares.offsite.OffsiteMiddle\ |                                      |
| ware`)                               |                                      |
+--------------------------------------+--------------------------------------+
| referer (:class:`~scrapy.spid\       |                                      |
| ermiddlewares.referer.RefererMiddle\ |                                      |
| ware`)                               |                                      |
+--------------------------------------+--------------------------------------+
| urllength (:class:`~scrapy.spid\     |                                      |
| ermiddlewares.urllength.UrlLengthMi\ |                                      |
| ddleware`)                           |                                      |
+--------------------------------------+--------------------------------------+
| **Downloader middlewares**                                                  |
+--------------------------------------+--------------------------------------+
| ajaxcrawl (:class:`~scrapy.download\ |                                      |
| ermiddlewares.ajaxcrawl.AjaxCrawlMi\ |                                      |
| ddleware`)                           |                                      |
+--------------------------------------+--------------------------------------+
| chunked (:class:`~scrapy.download\   |                                      |
| ermiddlewares.chunked.ChunkedTrans\  |                                      |
| ferMiddleware`)                      |                                      |
+--------------------------------------+--------------------------------------+
| cookies (:class:`~scrapy.download\   |                                      |
| ermiddlewares.cookies.CookiesMiddle\ |                                      |
| ware`)                               |                                      |
+--------------------------------------+--------------------------------------+
| defaultheaders (:class:`~scrapy.down\| Every configuration entry is treated |
| loadermiddlewares.defaultheaders.Def\| as a default header.                 |
| aultHeadersMiddleware`)              |                                      |
+--------------------------------------+--------------------------------------+
| **Extensions**                                                              |
+--------------------------------------+--------------------------------------+
| autothrottle                         | Installing sets                      |
| (:ref:`topics-autothrottle`)         | :setting:`AUTOTHROTTLE_ENABLED` to   |
|                                      | ``True``.                            |
+--------------------------------------+--------------------------------------+
| corestats (:class:`~scrapy.exten\    |                                      |
| sions.corestats.CoreStats`)          |                                      |
+--------------------------------------+--------------------------------------+
| closespider (:class:`~scrapy.exten\  |                                      |
| sions.closespider.CloseSpider`)      |                                      |
+--------------------------------------+--------------------------------------+
| debugger (:class:`~scrapy.exten\     |                                      |
| sions.debug.Debugger`)               |                                      |
+--------------------------------------+--------------------------------------+
| feedexport (:ref:`topics-feed-expor\ |                                      |
| ts`)                                 |                                      |
+--------------------------------------+--------------------------------------+
| logstats (:class:`~scrapy.exten\     |                                      |
| sions.logstats.LogStats`)            |                                      |
+--------------------------------------+--------------------------------------+
| memdebug (:class:`~scrapy.exten\     | Installing sets                      |
| sions.memdebug.MemoryDebugger`)      | :setting:`MEMDEBUG_ENABLED` to       |
|                                      | ``True``.                            |
+--------------------------------------+--------------------------------------+
| memusage (:class:`~scrapy.exten\     | Installing sets                      |
| sions.memusage.MemoryUsage`)         | :setting:`MEMUSAGE_ENABLED` to       |
|                                      | ``True``.                            |
+--------------------------------------+--------------------------------------+
| spiderstate (:class:`~scrapy.exten\  |                                      |
| sions.spiderstate.SpiderState`)      |                                      |
+--------------------------------------+--------------------------------------+
| stacktracedump (:class:`~scrapy.ext\ |                                      |
| ensions.debug.StackTraceDump`)       |                                      |
+--------------------------------------+--------------------------------------+
| statsmailer (:class:`~scrapy.exten\  |                                      |
| sions.statsmailer.StatsMailer`)      |                                      |
+--------------------------------------+--------------------------------------+
| telnetconsole (:ref:`topics-telnet\  |                                      |
| console`)                            |                                      |
+--------------------------------------+--------------------------------------+

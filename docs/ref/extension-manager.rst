.. _ref-extension-manager:

=================
Extension Manager
=================

.. module:: scrapy.extension
   :synopsis: The extension manager

The Extension Manager is responsible for loading and keeping track of installed
extensions and it's configured through the :setting:`EXTENSIONS` setting which
contains a dictionary of all available extensions and their order similar to
how you :ref:`configure the downloader middlewares
<topics-downloader-middleware-setting>`.

.. class:: ExtensionManager

    The extension manager is a singleton object, which is instantiated at module
    loading time and can be accessed like this::

        from scrapy.extension import extensions

    .. attribute:: loaded

        A boolean which is True if extensions are already loaded or False if
        they're not.

    .. attribute:: enabled

        A dict with the enabled extensions. The keys are the extension class names,
        and the values are the extension objects. Example::

            >>> from scrapy.extension import extensions
            >>> extensions.load()
            >>> print extensions.enabled
            {'CoreStats': <scrapy.stats.corestats.CoreStats object at 0x9e272ac>,
             'WebConsoke': <scrapy.management.telnet.TelnetConsole instance at 0xa05670c>,
            ...

    .. attribute:: disabled

        A dict with the disabled extensions. The keys are the extension class names,
        and the values are the extension class paths (because objects are never
        instantiated for disabled extensions). Example::

            >>> from scrapy.extension import extensions
            >>> extensions.load()
            >>> print extensions.disabled
            {'MemoryDebugger': 'scrapy.contrib.webconsole.stats.MemoryDebugger',
             'SpiderProfiler': 'scrapy.contrib.spider.profiler.SpiderProfiler',
            ...

    .. method:: load()

        Load the available extensions configured in the :setting:`EXTENSIONS`
        setting. On a standard run, this method is usually called by the Execution
        Manager, but you may need to call it explicitly if you're dealing with
        code outside Scrapy.

    .. method:: reload()

        Reload the available extensions. See :meth:`load`.

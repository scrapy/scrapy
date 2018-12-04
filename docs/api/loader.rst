.. _topics-api-spiderloader:

================
SpiderLoader API
================

.. module:: scrapy.loader
   :synopsis: The spider loader

.. class:: SpiderLoader

    This class is in charge of retrieving and handling the spider classes
    defined across the project.

    Custom spider loaders can be employed by specifying their path in the
    :setting:`SPIDER_LOADER_CLASS` project setting. They must fully implement
    the :class:`scrapy.interfaces.ISpiderLoader` interface to guarantee an
    errorless execution.

    .. method:: from_settings(settings)

       This class method is used by Scrapy to create an instance of the class.
       It's called with the current project settings, and it loads the spiders
       found recursively in the modules of the :setting:`SPIDER_MODULES`
       setting.

       :param settings: project settings
       :type settings: :class:`~scrapy.settings.Settings` instance

    .. method:: load(spider_name)

       Get the Spider class with the given name. It'll look into the previously
       loaded spiders for a spider class with name `spider_name` and will raise
       a KeyError if not found.

       :param spider_name: spider class name
       :type spider_name: str

    .. method:: list()

       Get the names of the available spiders in the project.

    .. method:: find_by_request(request)

       List the spiders' names that can handle the given request. Will try to
       match the request's url against the domains of the spiders.

       :param request: queried request
       :type request: :class:`~scrapy.http.Request` instance

===========================
Class Factory Methods
===========================

These methods create an instance of their implementer class by 
extracting the components needed for it from the argument that the method takes.

.. py:classmethod:: from_crawler(cls, crawler)

    Factory method that if present, is used to create an instance of the implementer class
    using a :class:`~scrapy.crawler.Crawler`. It must return a new instance
    of the implementer class. The Crawler object is needed in order to provide 
    access to all Scrapy core components like settings and signals; It is a 
    way for the implenter class to access them and hook its functionality into Scrapy.

    :param crawler: crawler that uses this middleware
    :type crawler: :class:`~scrapy.crawler.Crawler` object


.. py:classmethod:: from_settings(cls, settings)

    This class method is used by Scrapy to create an instance of the implementer class
    using the settings passed as arguments.
    This class method will not be called at all if from_crawler is defined.


    :param settings: project settings
    :type settings: :class:`~scrapy.settings.Settings` instance

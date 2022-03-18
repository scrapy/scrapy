===========================
Class Factory Methods
===========================

Factory methods create an instance of their implementer class by 
extracting the components needed for it from the argument that the method takes.
Throughout Scrapy the most common factory methods are ``from_crawler`` and ``from_settings`` where 
they each take one parameter namely, a crawler or a settings object respectively.


The ``from_crawler`` class method is implemented in the following objects:
    * ItemPipeline
    * DownloaderMiddleware
    * SpiderMiddleware
    * Scheduler
    * BaseScheduler
    * Spider

The ``from_settings`` class method is implemented in the following objects:
    * MailSender
    * SpiderLoader


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



Implementing Factory Methods
============================

While extending a class that implements one of these factory methods.
One's goal when extending these factory methods is simply given the arguments passed to it,
whether is crawler, settings or any additional ones; to create a class instance.
The main reason of including the Crawler object or the Settings object is because of the how much
information these objects hold and can be used in the instantiation of the class.

``Crawler`` specifically gives access to ``settings``, ``signals``, ``stats``, ``extensions``,
``engine``, and ``spider`` which maybe very useful when wanting to instantiate a class.

For example, lets say that we want to create a new spider, say TestSpider will look like this::

    class TestSpider:
        
        def __init__(self, ex1, ex2, ex3, name=None **kwargs):
            super().__init__(name, **kwargs)
            self.extra_param1: str = ex1
            self.extra_param2: int = ex2
            self.extra_param3: bool = ex3
        
        # Other methods are ommited for the sake of the example

        @classmethod
        def from_crawler(cls, crawler, ex1, ex2, ex3):
            # Do some configs if needed 
            # For example: 
            # first check if the extension should be enabled and raise
            # NotConfigured otherwise
            if not crawler.settings.getbool('MYEXT_ENABLED'):
                raise NotConfigured
            
            # E.g.: get the number of items from settings
            item_count = crawler.settings.getint('MYEXT_ITEMCOUNT', 1000)

            # Instantiate the extension object
            spider = cls(ex1, ex2, ex3)

            # Maybe connect the extension object to signals
            crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)

            # Validate some more settings
            my_settings_dict = crawler.settings.getdict(f'MYEXT_DICT'):
            if 'some_key' not in my_settings_dict:
                raise SomeException
            
            #.... 
            # Do some more configs if needed 
            #....
            
            # Finaly return the extension object
            return spider

Similarly, when one wants to extend a class that implements the ``from_settings`` method, it will
look similar to the following example. 
Say you want to create ::

    class MyNewSender:
        def __init__(self, is_enabled, send_at):
            self.is_enabled = is_enabled
            self.send_at = send_at
        
        #Some more methods...

        @classmethod
        def from_settings(cls, settings):
            # Get the needed values to instantiate the class from the settings object
            is_enabled = settings.getbool('MY_SENDER_ENABLED')
            send_at = settings.get("DATETIME_OF_SENDING")

            # ...
            # Maybe some more configs
            # ...
            
            # Finaly return the extension object
            return cls(is_enabled, send_at)

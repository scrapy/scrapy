.. _topics-storage:

=======
Storage
=======

The storage functionality can be used to store information locally or globally 
based on the events of opening and closing a spider. The original purpose of 
having the storage functionality is to be able to handle the cookie storage 
across spiders, however this can be extended for other purposes.

.. _topics-base-storage:

BaseStorage
=============

BaseStorage is the interface of the storage class that defines how an implemented 
storage should behave. The main methods are the following:

   .. method:: open_spider(spider)
This method is called upon the event of a spider being opened.

      :param spider: the spider that is being opened
      :type spider: :class:`~scrapy.Spider` object

   .. method:: close_spider(spider)
This method is called upon the event of a spider being closed.

      :param spider: the spider that is being closed
      :type spider: :class:`~scrapy.Spider` object

.. _topics-in-memory-storage:

InMemoryStorage
=============

The InMemoryStorage is designed to allow the storage of cookies on a local file.
If the COOKIES_PERSISTENCE constant is set to true in the settings of the project,
the cookies are saved to a file and loaded from it on demand.

   .. method:: open_spider(spider)
This method is called upon the event of a spider being opened. When the spider is 
opened, the cookies are loaded from the file, if they were saved there by a spider 
from a previous crawling session.

      :param spider: the spider that is being opened
      :type spider: :class:`~scrapy.Spider` object

   .. method:: close_spider(spider)
This method is called upon the event of a spider being closed. When the spider is 
closed, the cookies are saved to the file in order to allow another spider to reuse 
those existing cookies at a later point in time.

      :param spider: the spider that is being closed
      :type spider: :class:`~scrapy.Spider` object
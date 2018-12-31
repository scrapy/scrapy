.. _topics-scheduler:

=========
Scheduler
=========

The Scheduler receives requests from the :ref:`Engine <component-engine>` and enqueues them into disk and/or disk queues
(:meth:`scrapy.core.scheduler.Scheduler.enqueue_request`).
It also gets those requests and feeds them back when the engine requests them (:meth:`scrapy.core.scheduler.Scheduler.next_request`).

Overriding the default Scheduler
================================

You can use your own custom Scheduler class by supplying the full Python path in the :setting:`SCHEDULER` setting


Scheduler interface
===================

This is the basic Scheduler API, i.e. the methods that are defined in the default Scheduler.

.. module:: scrapy.core.scheduler

.. class:: Scheduler(dupefilter, jobdir=None, dqclass=None, mqclass=None, logunser=False, stats=None, pqclass=None)

   :param dupefilter: An object responsible for checking requests and filter duplicates.
                      :setting:`DUPEFILTER_CLASS` is used by default.
   :type dupefilter: class
    
   :param jobdir: Path to a directory used to persist the crawl. See :ref:`topics-jobs`.
   :type jobdir: str

   :param dqclass: The class to be used as disk queue to store requests.
                   :setting:`SCHEDULER_DISK_QUEUE` is used by default.
   :type dqclass: class

   :param mqclass: The class to be used as memory queue to store requests.
                   :setting:`SCHEDULER_MEMORY_QUEUE` is used by default.
   :type mqclass: class

   :param logunser: A boolean flag indicating whether or not unserializable requests should be logged.
                    See :setting:`SCHEDULER_DEBUG`.
   :type logunser: bool

   :param stats: The class to be used to collect stats.
                 :setting:`STATS_CLASS` is used by default.
   :type stats: class

   :param pqclass: The class to be used as priority queue to store requests.
                   :setting:`SCHEDULER_PRIORITY_QUEUE` is used by default.
   :type pqclass: class

   .. method:: from_crawler(cls, crawler)

      If present, this ``classmethod`` is called from the Engine to create the Scheduler instance.
      The default implementation takes care of reading the settings mentioned in the constructor
      and loading the necessary classes and objects.

   .. method:: open(spider)

      This method is called when the Spider is opened by the Engine. It receives the Spider instance as 
      argument and it's useful to execute initialization code.
      
      The default implementation: 1) initializes the memory queue, 2) initializes the disk queue
      if the ``jobdir`` argument passed to the constructor was a valid directory, 3) returns the
      result of the dupefilter's ``open`` method.

      :param spider: the spider object for the current crawl
      :type spider: :class:`~scrapy.spiders.Spider` object

   .. method:: close(reason)

      This method is called when the Spider is closed by the Engine. It receives the reason why the crawl
      finished as argument and it's useful to execute cleaning code.

      The default implementation: 1) dumps pending requests to disk if the ``jobdir`` argument passed
      to the constructor was a valid directory, 2) returns the result of the dupefilter's ``close`` method.

      :param reason: a string which describes the reason why the spider was closed.
      :type reason: :class:`str` object

   .. method:: has_pending_requests()

      A predicate that is true if the Scheduler still has enqueued requests, false otherwise.

   .. method:: enqueue_request(request)
   
      Receives a :class:`~scrapy.http.Request` object. If the request is valid (i.e. it should not be
      filtered out by the Dupefilter) this method tries to push it into the disk queue, falling back
      to pushing it into the memory queue.
      
      This method is responsible for incrementing the appropriate stats (``scheduler/enqueued``,
      ``scheduler/enqueued/disk``, ``scheduler/enqueued/memory``).

      Returns ``True`` if the request was scheduled, ``False`` otherwise.

   .. method:: next_request()

      Get a request from the memory queue. If there are no more requests stored in memory,
      fall back to getting a request from the disk queue.

      This method is responsible for incrementing the appropriate stats (``scheduler/dequeued``,
      ``scheduler/dequeued/disk``, ``scheduler/dequeued/memory``).
      
      Returns a :class:`~scrapy.http.Request` object, or ``None`` if there are no more enqueued requests.

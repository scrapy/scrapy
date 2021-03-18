.. _topics-scheduler:

=========
Scheduler
=========

The Scheduler receives requests from the :ref:`Engine <component-engine>`
and enqueues them into disk and/or disk queues
(:meth:`scrapy.core.scheduler.Scheduler.enqueue_request`).
It also gets those requests and feeds them back when the engine requests
them (:meth:`scrapy.core.scheduler.Scheduler.next_request`).

Overriding the default Scheduler
================================

You can use your own custom `Scheduler` class by supplying the full
Python path in the :setting:`SCHEDULER` setting


Scheduler interface
===================

This is the basic Scheduler API, i.e. the methods that are defined in the default Scheduler.

.. module:: scrapy.core.scheduler

.. autoclass:: Scheduler

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

   .. automethod:: from_crawler

   .. automethod:: open

   .. automethod:: close

   .. automethod:: has_pending_requests

   .. automethod:: enqueue_request

   .. automethod:: next_request

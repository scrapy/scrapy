.. _topics-scheduler:

=========
Scheduler
=========

.. module:: scrapy.core.scheduler

The **scheduler** is a :ref:`component <topics-components>` that :ref:`stores
pending requests, drops unwanted requests, and determines in which order
pending requests are sent <scheduler-responsibilities>`.

It is set in the :setting:`SCHEDULER` setting. There is only 1 built-in
scheduler, :class:`~scrapy.core.scheduler.Scheduler`, but you can
:ref:`implement your own <custom-scheduler>`.

.. _scheduler-responsibilities:

Scheduler responsibilities
==========================

A scheduler must:

-   Store pending requests.

    The built-in scheduler stores requests in memory or disk. Other schedulers
    may rely, for example, on frontier, queue, database or storage services.

    Pending requests may come from the
    :ref:`Spider.start <scrapy.spiders.Spider.start>` method, from spider
    callbacks (:attr:`Request.callback <scrapy.Request.callback>`),
    from :ref:`spider middlewares <topics-spider-middleware>` or from
    :ref:`downloader middlewares <topics-downloader-middleware>`.

-   Drop unwanted requests.

    It is recommended for schedulers to use the configured
    :setting:`DUPEFILTER_CLASS` and take into account
    :attr:`Request.dont_filter <scrapy.Request.dont_filter>`, but schedulers
    may follow different criteria for dropping requests.

-   Return requests in the order they should be sent.

    To determine the right order, schedulers may take into account
    :attr:`Request.priority <scrapy.Request.priority>` and applicable built-in
    settings (e.g. :setting:`SCHEDULER_PRIORITY_QUEUE`,
    :setting:`SCHEDULER_MEMORY_QUEUE`, :setting:`SCHEDULER_DISK_QUEUE`), but
    schedulers may also ignore any of those parameters at will.

Built-in components
===================

Built-in scheduler
------------------

.. autoclass:: Scheduler()


.. _priority-queues:

Built-in priority queues
------------------------

Components for :setting:`SCHEDULER_PRIORITY_QUEUE`:

.. autoclass:: scrapy.pqueues.ScrapyPriorityQueue()
.. autoclass:: scrapy.pqueues.DownloaderAwarePriorityQueue()


.. _memory-queues:

Built-in memory queues
----------------------

Components for :setting:`SCHEDULER_MEMORY_QUEUE`:

.. autoclass:: scrapy.squeues.FifoMemoryQueue()
.. autoclass:: scrapy.squeues.LifoMemoryQueue()


.. _disk-queues:

Built-in disk queues
--------------------

Components for :setting:`SCHEDULER_DISK_QUEUE`:

.. autoclass:: scrapy.squeues.PickleFifoDiskQueue()
.. autoclass:: scrapy.squeues.PickleLifoDiskQueue()
.. autoclass:: scrapy.squeues.MarshalFifoDiskQueue()
.. autoclass:: scrapy.squeues.MarshalLifoDiskQueue()


Writing custom components
=========================

.. _custom-scheduler:

Writing a scheduler
-------------------

Schedulers should subclass :class:`BaseScheduler` and implement its abstract
methods:

.. autoclass:: BaseScheduler
    :members:
    :member-order: bysource


.. _custom-priority-queue:

Writing a priority queue
------------------------

.. autoclass:: scrapy.pqueues.PriorityQueueProtocol()
    :members:
    :special-members: __init__, __len__
    :member-order: bysource

.. _custom-internal-queue:

Writing an internal queue
-------------------------

.. autoclass:: scrapy.pqueues.QueueProtocol()
    :members:
    :special-members: __len__
    :member-order: bysource

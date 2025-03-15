.. _topics-scheduler:

=========
Scheduler
=========

.. module:: scrapy.core.scheduler

The **scheduler** is a :ref:`component <topics-components>` that stores pending
requests, drops unwanted requests, and determines in which order pending
requests are sent.

It is set in the :setting:`SCHEDULER` setting.

Pending requests may come from seeding (see :setting:`SEEDING_POLICY`),
spider callbacks (:attr:`Request.callback <scrapy.Request.callback>`),
:ref:`spider middlewares <topics-spider-middleware>` or :ref:`downloader
middlewares <topics-downloader-middleware>`.

How requests are **stored** depends on the scheduler. The built-in scheduler,
:class:`~scrapy.core.scheduler.Scheduler`, can store requests in memory or
disk. Other schedulers may rely, for example, on frontier, queue, database or
storage services.

Which requests are **dropped** also depends on the scheduler. It is recommended
for schedulers to use the configured :setting:`DUPEFILTER_CLASS` and take into
account :attr:`Request.dont_filter <scrapy.Request.dont_filter>`, but
schedulers are free to follow their own criteria for dropping requests.

How requests are **prioritized**, i.e. in which order they are sent, depends on
the scheduler as well. Schedulers may take into account :attr:`Request.priority
<scrapy.Request.priority>` and applicable built-in settings (e.g.
:setting:`SCHEDULER_PRIORITY_QUEUE`, :setting:`SCHEDULER_MEMORY_QUEUE`,
:setting:`SCHEDULER_DISK_QUEUE`), but schedulers may also ignore any of those
parameters at will.

Built-in scheduler
==================

.. autoclass:: Scheduler()


Writing a scheduler
===================

.. tip:: Before writing a custom scheduler, see
    :class:`~scrapy.core.scheduler.Scheduler` to learn how to customize the
    default scheduler.

Schedulers should subclass :class:`BaseScheduler` and implement its abstract
methods:

.. autoclass:: BaseScheduler
   :members:
   :member-order: bysource

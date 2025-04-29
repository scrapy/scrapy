.. _topics-scheduler:

=========
Scheduler
=========

.. module:: scrapy.core.scheduler

The scheduler component receives requests from the :ref:`engine <component-engine>`
and stores them into persistent and/or non-persistent data structures.
It also gets those requests and feeds them back to the engine when it
asks for a next request to be downloaded.


Overriding the default scheduler
================================

You can use your own custom scheduler class by supplying its full
Python path in the :setting:`SCHEDULER` setting.


Minimal scheduler interface
===========================

.. autoclass:: BaseScheduler
   :members:


Default Scrapy scheduler
========================

.. autoclass:: Scheduler
   :members:
   :special-members: __len__

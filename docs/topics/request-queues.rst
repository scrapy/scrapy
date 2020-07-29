.. _topics-request-queues:

==============
Request Queues
==============

Scrapy uses queues to store requests and to decide what request to schedule
next. The scheduler does not use a specific queue implementation (called
*downstream queue*) directly but instead the downstream queue is wrapped by a
priority queue.

Priority Queues
===============

Priority queues make sure that requests with the highest priority are scheduled
first. For this purpose, a priority queue uses multiple downstream queues---one
for each priority. The setting :setting:`SCHEDULER_PRIORITY_QUEUE` determines
the type of priority queue that will be used by the scheduler.

Scrapy comes with two priority queue implementations:

  * ``'scrapy.pqueues.ScrapyPriorityQueue'``
  * ``'scrapy.pqueues.DownloaderAwarePriorityQueue'``

The default priority queue is ``'scrapy.pqueues.ScrapyPriorityQueue'`` and works
best during single-domain crawls (see also
:ref:`broad-crawls-scheduler-priority-queue`). For crawling multiple different
domains in parallel the recommended priority queue is
``'scrapy.pqueues.DownloaderAwarePriorityQueue'``. This priority queue takes
downloader activity into account: Domains with the least amount of active
downloads are dequeued first.

Downstream Queues
=================

Scrapy differentiates between two types of downstream queues: memory queues and
disk queues. If the :setting:`JOBDIR` setting is defined, a disk queue is used.
If it is not defined, a memory queue is used (this is the default).

Memory queue
------------

Memory queues do not require additional configuration or additional storage and
are therefore used by default. The default for :setting:`SCHEDULER_MEMORY_QUEUE`
is ``'scrapy.squeues.LifoMemoryQueue'``.

Disk queue
----------

With disk queues it is possible to :ref:`pause and resume crawls <topics-jobs>`
and schedule more requests than fit in memory. The default for
:setting:`SCHEDULER_DISK_QUEUE` is ``'scrapy.squeues.PickleLifoDiskQueue'``.

Disk queues serialize requests, e.g. using :meth:`pickle.serialize`. If
serialization fails, the scheduler falls back to a memory queue.

.. note::

    :setting:`JOBDIR` has to be set so that the scheduler uses the disk queue
    configured by :setting:`SCHEDULER_DISK_QUEUE`.

Interface
---------

If you want to use your own disk queue implementation, it has to conform to
the following interface:

.. class:: MyExternalQueue

   .. classmethod:: from_crawler(cls, crawler, key)

      Creates a new queue object based on ``crawler`` and ``key``.

      This factory method receives the ``crawler`` argument to access the
      crawler's settings and the ``key`` argument which identifies the queue.
      The class method creates and returns a queue object based on the
      arguments.

      The method is expected to verify the arguments and the relevant settings
      and raise an exception in case of an error. This may involve opening
      a connection to a remote service.

      .. note::
         In case an exception is raised, the crawling process is halted.

      :raises Exception: If ``key`` or a queue-specific setting is invalid.

   .. method:: push(self, request)

      Pushes a request to the queue.

      The helper function :meth:`~scrapy.utils.reqser.request_to_dict` can be
      used to convert the request to a dict which can then be easily
      serialized with, for example, :meth:`pickle.dumps`.

      The scheduler will fall back to the memory queue (for this particular
      request) in case of a :exc:`TransientError` or a
      :exc:`SerializationError`. In case of any other exception the crawling
      process is halted.

      :raises TransientError: If pushing to the queue failed due to a
          temporary error (e.g. the connection was dropped).
      :raises SerializationError: If pushing to the queue failed because the
          request could not be serialized.

   .. method:: pop(self)

      Pops a request from the queue. In case of a temporary problem, ``None``
      is returned.

      The helper function :meth:`~scrapy.utils.reqser.request_from_dict` can
      be used to convert the deserialized dict back to a request.

      It is up to the queue implementation to decide if the most recently
      pushed value (LIFO) or the least recently pushed value (FIFO) is
      returned.

      .. note::
         In case of a temporary error, the method must not raise an exception
         but return ``None`` instead.

   .. method:: close(self)

      Releases internal resources (e.g. closes a file or socket).

   .. method:: __len__(self)

      Returns the number of elements in the queue.

      If the number of elements cannot be determined (e.g. because of a
      connection problem), the method must not return 0 because this would
      cause the queue to be closed.

      .. note::
         In case of a temporary error, the method must not raise an exception
         but return the number of elements instead.

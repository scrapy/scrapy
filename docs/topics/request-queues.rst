.. _topics-request-queues:

==============
Request queues
==============

.. _priority-queues:
.. setting:: SCHEDULER_PRIORITY_QUEUE

Priority queues
===============

.. currentmodule:: scrapy.pqueues

To decide the order in which requests are sent, Scrapy uses a queue called the
*priority queue*.

The :setting:`SCHEDULER_PRIORITY_QUEUE` setting determines the type of priority
queue that Scrapy uses. Its default value is :class:`ScrapyPriorityQueue`.

Scrapy provides the following priority queue implementations:

.. autoclass:: DownloaderAwarePriorityQueue

.. autoclass:: ScrapyPriorityQueue


.. setting:: SCHEDULER_DISK_QUEUE
.. setting:: SCHEDULER_MEMORY_QUEUE
.. _downstream-queues:

Downstream queues
=================

.. currentmodule:: scrapy.squeues

A :ref:`priority queue <priority-queues>` uses queues internally to store
pending requests. These internal queues are called *downstream queues*.

The organization method used by the downstream queues, usually either
FIFO or LIFO, affects the order in which requests are sent for requests
that the :ref:`priority queue <priority-queues>` considers to have the same
priority.

The type of downstream queue used depends on the :setting:`JOBDIR` setting (see
:ref:`topics-jobs`):

-   If :setting:`JOBDIR` is not set (default), the memory downstream queue type
    defined in the :setting:`SCHEDULER_MEMORY_QUEUE` setting is used, which
    defaults to :class:`LifoMemoryQueue`.

    Scrapy provides the following memory downstream queue classes:

    .. autoclass:: FifoMemoryQueue

    .. autoclass:: LifoMemoryQueue

-   If :setting:`JOBDIR` is set, the disk downstream queue from the
    :setting:`SCHEDULER_DISK_QUEUE` setting is used instead, which defaults to
    :class:`PickleLifoDiskQueue`.

    In addition to request order, which disk downstream queue you use can
    affect request serialization speed (CPU usage) and size (disk usage). See
    “Comparison with ``marshal``” in the documentation of :mod:`pickle` for
    more information.

    When request serialization fails, Scrapy falls back to using a memory
    downstream queue.

    Scrapy provides the following disk downstream queue classes:

    .. autoclass:: MarshalFifoDiskQueue

    .. autoclass:: MarshalLifoDiskQueue

    .. autoclass:: PickleFifoDiskQueue

    .. autoclass:: PickleLifoDiskQueue


Writing your own disk downstream queue class
--------------------------------------------

If you want to define and use your own disk downstream queue implementation,
it has to conform to the following interface:

.. class:: MyExternalQueue

   .. classmethod:: from_crawler(cls, crawler: scrapy.crawler.Crawler, key: str)

      Return an instance of this disk downstream queue class.

      *key* is the unique ID of the disk downstream queue instance. It may be
      used, for example, to create a unique file or folder to store the queue
      content.

      If the input data is invalid, raise an exception from this class method
      of from your ``__init__`` method to halt the crawl.

   .. method:: push(self, request: scrapy.http.Request)

      Push a request into the queue.

      The helper function :func:`~scrapy.utils.reqser.request_to_dict` can be
      used to convert the request into a dict that can then be easily
      serialized with, for example, :func:`pickle.dumps`.

      Scrapy falls back to the memory downstream queue for *request* if one of
      the following exceptions is raised:

      -     :exc:`TransientError`: indicates a temporary failure.

            For example, if storing requests on a server, raise this exception
            if you temporarily loose access to the server.

        -   :exc:`SerializationError`: indicates that *request* could not be
            serialized

   .. method:: pop(self)

      Pop a request from the queue.

      In case of a temporary problem, ``None`` is returned. In all other cases,
      an exception is raised, causing the crawling process to halt.

      The helper function :func:`~scrapy.utils.reqser.request_from_dict` can
      be used to convert a deserialized dict back into a
      :class:`~scrapy.http.Request` object.

   .. method:: close(self)

      Release internal resources (e.g. close files or sockets).

   .. method:: __len__(self)

      Return the number of requests in the queue.

      If the number of requests cannot be determined (e.g. because of a
      connection problem), the method should neither return 0, which would
      cause the queue to be closed, nor raise an exception, which would halt
      the crawl.

.. autofunction:: scrapy.utils.reqser.request_from_dict

.. autofunction:: scrapy.utils.reqser.request_to_dict

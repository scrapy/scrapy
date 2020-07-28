.. _topics-request-queues:

==============
Request Queues
==============

Scrapy uses queues to schedule requests. By default, a memory-based queue is
used but if :ref:`crawls should be paused and resumed <topics-jobs>` or more
requests than fit in memory are scheduled, using an external queue (disk
queue) is necessary. The setting :setting:`SCHEDULER_DISK_QUEUE` determines
the type of disk queue that will be used by the scheduler.

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

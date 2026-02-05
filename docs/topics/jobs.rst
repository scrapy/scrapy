.. _topics-jobs:

=================================
Jobs: pausing and resuming crawls
=================================

Sometimes, for big sites, it's desirable to pause crawls and be able to resume
them later.

Scrapy supports this functionality out of the box by providing the following
facilities:

* a scheduler that persists scheduled requests on disk

* a duplicates filter that persists visited requests on disk

* an extension that keeps some spider state (key/value pairs) persistent
  between batches

.. _job-dir:

Job directory
=============

To enable persistence support, define a *job directory* through the
:setting:`JOBDIR` setting.

The job directory will store all required data to keep the state of a *single*
job (i.e. a spider run), so that if stopped cleanly, it can be resumed later.

.. warning:: This directory must *not* be shared by different spiders, or even
    different jobs of the same spider.

See also :ref:`job-dir-contents`.

How to use it
=============

To start a spider with persistence support enabled, run it like this::

    scrapy crawl somespider -s JOBDIR=crawls/somespider-1

Then, you can stop the spider safely at any time (by pressing Ctrl-C or sending
a signal), and resume it later by issuing the same command::

    scrapy crawl somespider -s JOBDIR=crawls/somespider-1

.. _topics-keeping-persistent-state-between-batches:

Keeping persistent state between batches
========================================

Sometimes you'll want to keep some persistent spider state between pause/resume
batches. You can use the ``spider.state`` attribute for that, which should be a
dict. There's :ref:`a built-in extension <topics-extensions-ref-spiderstate>`
that takes care of serializing, storing and loading that attribute from the job
directory, when the spider starts and stops.

Here's an example of a callback that uses the spider state (other spider code
is omitted for brevity):

.. code-block:: python

    def parse_item(self, response):
        # parse item here
        self.state["items_count"] = self.state.get("items_count", 0) + 1

Persistence gotchas
===================

There are a few things to keep in mind if you want to be able to use the Scrapy
persistence support:

Cookies expiration
------------------

Cookies may expire. So, if you don't resume your spider quickly the requests
scheduled may no longer work. This won't be an issue if your spider doesn't rely
on cookies.


.. _request-serialization:

Request serialization
---------------------

For persistence to work, :class:`~scrapy.Request` objects must be
serializable with :mod:`pickle`, except for the ``callback`` and ``errback``
values passed to their ``__init__`` method, which must be methods of the
running :class:`~scrapy.Spider` class.

If you wish to log the requests that couldn't be serialized, you can set the
:setting:`SCHEDULER_DEBUG` setting to ``True`` in the project's settings page.
It is ``False`` by default.

.. _job-dir-contents:

Job directory contents
======================

The contents of a job directory depend on the components used during the job.
Components known to write in the job directory include the :ref:`scheduler
<topics-scheduler>` and the :class:`~scrapy.extensions.spiderstate.SpiderState`
extension. See the reference documentation of the corresponding components for
details.

For example, with default settings, the job directory may look like this:

.. code-block:: none

    ├── requests.queue
    |   ├── active.json
    |   └── {hostname}-{hash}
    |       └── {priority}{s?}
    |           ├── q{00000}
    |           └── info.json
    ├── requests.seen
    └── spider.state

Where:

-   :class:`~scrapy.core.scheduler.Scheduler` creates the ``requests.queue/``
    directory and the ``active.json`` file, the latter containing the state
    data returned by :meth:`DownloaderAwarePriorityQueue.close()
    <scrapy.pqueues.DownloaderAwarePriorityQueue.close>` the last time the job
    was paused.

-   :class:`~scrapy.pqueues.DownloaderAwarePriorityQueue` creates the
    ``{hostname}-{hash}`` directories.

-   :class:`~scrapy.pqueues.ScrapyPriorityQueue` creates the ``{priority}{s?}``
    directories.

-   :class:`scrapy.squeues.PickleLifoDiskQueue`, a subclass of
    :class:`queuelib.LifoDiskQueue` that uses :mod:`pickle` to serialize
    :class:`dict` representations of :class:`scrapy.Request` objects, creates
    the ``info.json`` and ``q{00000}`` files.

-   :class:`~scrapy.dupefilters.RFPDupeFilter` creates the ``requests.seen``
    file.

-   :class:`~scrapy.extensions.spiderstate.SpiderState` creates the
    ``spider.state`` file.

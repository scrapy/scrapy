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

Job directory
=============

To enable persistence support you just need to define a *job directory* through
the ``JOBDIR`` setting. This directory will be for storing all required data to
keep the state of a single job (i.e. a spider run).  It's important to note that
this directory must not be shared by different spiders, or even different
jobs/runs of the same spider, as it's meant to be used for storing the state of
a *single* job.

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

.. _topics-jobdir-structure:

JOBDIR file structure
======================

When you enable job persistence by setting :setting:`JOBDIR`, Scrapy creates
several files and directories inside the specified job directory to maintain
the crawl state. Understanding these files can help you troubleshoot issues
and manage your crawls more effectively.

The following files and directories are created inside the ``JOBDIR``:

``requests.seen``
-----------------

A text file that stores fingerprints of all requests that have been processed
by the duplicate filter. Each line contains a hexadecimal fingerprint of a
request.

This file is used by the :class:`~scrapy.dupefilters.RFPDupeFilter` to prevent
processing the same request multiple times when a crawl is resumed. The
fingerprint is calculated based on the request's URL, method, and body.

The file is written line-by-line as requests are processed, and loaded back
into memory when the crawl is resumed.

``requests.queue/``
-------------------

A directory containing the disk-based priority queue for pending requests.
This directory is only created when :setting:`JOBDIR` is set, allowing Scrapy
to persist requests that haven't been processed yet.

The scheduler stores serialized requests in this directory, organized by
priority. When a crawl is resumed, these requests are loaded back into the
scheduler and processed.

Files inside this directory:

* ``active.json``: A JSON file tracking which priority queues are active
* ``p<priority>/``: Directories for each priority level containing queued requests

Requests that cannot be serialized (e.g., those with lambda callbacks) are
kept in memory only and will be lost if the crawl is interrupted.

``spider.state``
----------------

A pickle file that stores the spider's persistent state dictionary
(``spider.state``). This file is managed by the
:ref:`SpiderState extension <topics-extensions-ref-spiderstate>`.

You can use this to store custom data that should persist between crawl
runs, such as counters, timestamps, or other spider-specific information.

Example files
-------------

Here's what a typical ``JOBDIR`` might look like after running a crawl::

    crawls/somespider-1/
    ├── requests.seen          # Duplicate filter data
    ├── requests.queue/        # Pending requests
    │   ├── active.json        # Active priority queues
    │   ├── p0/                # Priority 0 requests
    │   └── p1/                # Priority 1 requests
    └── spider.state           # Spider state data

.. note::

   The ``JOBDIR`` should be unique for each spider run. Don't reuse the same
   directory for different spiders or different runs of the same spider unless
   you want to resume that specific crawl.

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

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

Files created in JOBDIR
=======================

When you enable job persistence, Scrapy creates several files inside the ``JOBDIR``
to store the state of your crawl. Understanding these files can help you debug
issues and manage your crawls effectively.

requests.seen
-------------

This file contains SHA1 fingerprints of URLs that have been processed (one per line).
It is used by the :class:`~scrapy.dupefilters.RFPDupeFilter` to prevent crawling
the same URL twice.

**Structure**: Plain text file with one SHA1 hash per line.

**Usage**: When Scrapy resumes a crawl, it reads this file to rebuild the in-memory
set of visited URLs. The file is appended to in real-time as requests are processed.

Example content::

    198e506499442eaaaa6027b27f648b1fa2d4b636
    8c78883bc76ebe66d1cf7e05306ff9438d340785
    694b550106be20910b0ede19fcdcdb5d9fea8542

requests.queue
--------------

This directory contains the pending requests that have been scheduled but not yet
processed. The structure is managed by the scheduler's priority queue implementation
(by default :class:`~scrapy.pqueues.ScrapyPriorityQueue`).

**Structure**: The directory contains:

* ``active.json``: Metadata about active priority queues, mapping hostnames to their
  priority levels. Example: ``{"www.example.com": [6, 7], "www.github.com": [7]}``

* ``{hostname}-{hash}/``: Subdirectories for each download slot, named with a
  filesystem-safe hostname and its MD5 hash to prevent collisions.

  * ``{priority}/``: Subdirectories for each priority level.

    * ``q000000``, ``q000001``, etc.: Binary files containing serialized (pickled)
      request objects, managed by the `queuelib <https://github.com/scrapy/queuelib>`_
      library.

    * ``info.json``: Metadata about the queue files (e.g., ``{"chunksize": 100000,
      "size": 28, "tail": [0, 18, 4986], "head": [0, 46]}``). Written only on clean
      shutdown.

**Note**: The ``active.json`` and ``info.json`` files are only written when the
spider closes cleanly. If the spider crashes, these files may be missing or outdated,
but Scrapy can still recover pending requests from the ``q*`` files.

spider.state
------------

This file contains the pickled contents of the ``spider.state`` dictionary, which
allows spiders to persist custom data between runs.

**Structure**: Binary file containing a pickled Python dictionary.

**Usage**: Read when the spider starts and written when it closes cleanly. By default,
Scrapy spiders have an empty state dictionary, so this file will contain an empty
dict unless your spider explicitly uses ``spider.state``.

Example (when unpickled): ``{}`` for an empty state, or ``{"items_count": 42,
"last_page": "https://example.com/page/5"}`` if your spider stores custom data.

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

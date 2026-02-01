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

.. _topics-jobdir-files:

Understanding JOBDIR Files
==========================

When you enable job persistence using the :setting:`JOBDIR` setting, Scrapy 
creates several files in the specified directory to maintain the crawler's state. 
Understanding these files can help you troubleshoot issues and manage disk space 
for large crawls.

Files and directories created
-----------------------------

**requests.queue/**
    A directory containing the queue of requests that are scheduled to be processed.
    Scrapy stores request objects here using Python's :mod:`pickle` module. The queue
    is split into multiple files (``p0``, ``p1``, etc.) to handle large numbers of
    requests efficiently.
    
    When you resume a crawl, Scrapy reads from this queue to continue where it left off.

**requests.seen**
    A file containing fingerprints (unique identifiers) of all requests that have been
    scheduled or processed. This is used by the :ref:`duplicates filter <topics-request-fingerprints>`
    to prevent the same URL from being crawled multiple times.
    
    The fingerprints are stored as a pickled set for fast lookup. For large crawls,
    this file can grow significantly in size.

**spider.state**
    Contains the spider's persistent state dictionary (``spider.state``). This file
    stores any custom data you save to ``spider.state`` between pause/resume cycles.
    See :ref:`topics-keeping-persistent-state-between-batches` for more information.

Example JOBDIR structure
------------------------

After running a spider with ``JOBDIR=crawls/myspider-1``, your directory structure 
will look like this::

    crawls/myspider-1/
    ├── requests.queue/
    │   ├── p0
    │   ├── p1
    │   └── ...
    ├── requests.seen
    └── spider.state

Important notes
---------------

* **Do not manually edit** these files - they use Python's :mod:`pickle` format and 
  manual editing will corrupt them.
  
* **One JOBDIR per spider run** - Each spider job should use a unique JOBDIR path. 
  Sharing a JOBDIR between different spiders or multiple runs of the same spider 
  will cause data corruption.
  
* **Disk space** - For large crawls with millions of URLs, the ``requests.queue/`` 
  directory and ``requests.seen`` file can consume significant disk space.
  
* **Fresh start** - To start a completely fresh crawl, delete the entire JOBDIR 
  folder before running the spider.

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
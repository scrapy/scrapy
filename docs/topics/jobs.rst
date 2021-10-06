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

For mode details about the layout of ``JOBDIR`` see :ref:`jobdir-details`.

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
dict. There's a built-in extension that takes care of serializing, storing and
loading that attribute from the job directory, when the spider starts and
stops.

Here's an example of a callback that uses the spider state (other spider code
is omitted for brevity)::

    def parse_item(self, response):
        # parse item here
        self.state['items_count'] = self.state.get('items_count', 0) + 1

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

.. _jobdir-details:

Job directory details
=====================

(using the DownloaderAwarePriorityQueue)::

  {crawlname}
    requests.queue
      active.json
      {hostname}-{hash}
        {priority}
          info.json
          q{00000}
    requests.seen
    spider.state


requests.queue
--------------
This directory contains requests that have been queued by the crawler but haven't been downloaded yet.

active.json
-----------
This file contains a dump of the scheduler's on-disk priority queue metadata. By default, this is provided by the `scrapy.pqueues.ScrapyPriorityQueue <https://docs.scrapy.org/en/latest/topics/settings.html?highlight=SCHEDULER_PRIORITY_QUEUE#scheduler-priority-queue>`_  class.

Scrapy implements priority queues by keeping a list of functionally separate FIFO queues that each have a priority number assigned to them. The scheduler needs to keep track of these queue/priority mappings in order to load the queues from disk and pick up where it left off.

(Is this actually true? It seems to me like all of this information can be recovered from the directory structure itself since the priorities are used for the sub-directory names)

This file is only written to disk when the crawler is closed cleanly. If the crawler resumes but cannot access this file, it will not be able to load the requests.queue or recover any of the pending requests.

Example::

    {"www.scrapy.org": [6, 7], "www.github.com": [7]}

{hostname}-{hash}
-----------------

A sub-directory for a single slot in the crawler. The name is a filesystem-safe encoding of the hostname, along with the hostname's md5-hash to prevent rare collisions between hostnames.

(why not just use the md5-hash? It seems pointlessly complex to add the human readable hostname component.)

qXXXXXX
-------
The file structure of the disk-backed queues are implemented by the `queuelib <https://github.com/scrapy/queuelib>`_ library. Request objects that are pushed to the queue are serialized (using pickle by default) and packed into a binary file format that's chunked across multiple files. I won't get into the gritty details but the general format of the q000000, q000001, etc. files looks like this::

  [size header][pickled request][size header][pickled request]...

The queue files are updated in real-time as requests are pushed to and popped from the python queues. This is optimized using some fancy read/write filesystem operations.

info.json
---------

The info.json file is written by `queuelib <https://github.com/scrapy/queuelib>`_ and contains some metadata about the queue files in that directory. This file is only written when if the queue is closed cleanly.

Example::

   {"chunksize": 100000, "size": 28, "tail": [0, 18, 4986], "head": [0, 46]}

(It's possible to read the queue files `directly <https://github.com/michael-lazar/mozz-archiver/blob/master/mozz_archiver/scripts/recover-queue>`_ without this metadata. Would it be possible to rebuild this info.json after a crash?)

requests.seen
-------------
This file contains a list of SHA1 fingerprints for URLs that have been crawled. It's used by `scrapy.dupefilters.RFPDupeFilter <https://docs.scrapy.org/en/latest/topics/settings.html?highlight=request_fingerprint#dupefilter-class>`_ to avoid crawling the same URL twice.

Scrapy opens the file in a+ mode and appends a new line after each request is downloaded with the hash of the request URL. The file is never flushed, but will be closed cleanly if scrapy is shut down safely.

Scrapy also stores a copy of the fingerprints in-memory using a set() structure for efficient comparison. When scrapy resumes a crawl, it will re-populate the internal list of fingerprints from the file.

Example::

  198e506499442eaaaa6027b27f648b1fa2d4b636
  8c78883bc76ebe66d1cf7e05306ff9438d340785
  694b550106be20910b0ede19fcdcdb5d9fea8542
  6a83389c45ba0423d51c9295988ec954f2ecfffe

spider.state
------------

This file contains the pickled value of spider.state. This is a dictionary that is available for spider implementations to store custom data. By default, scrapy spiders do not use state and this value will be an empty dictionary.

Scrapy will attempt to read from this file when opening a spider, and will dump the contents of the state to the file when the spider is closed cleanly.

Example::

  \x80\x04}\x94.

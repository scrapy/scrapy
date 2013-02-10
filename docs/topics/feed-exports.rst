.. _topics-feed-exports:

============
Feed exports
============

.. versionadded:: 0.10

One of the most frequently required features when implementing scrapers is
being able to store the scraped data properly and, quite often, that means
generating a "export file" with the scraped data (commonly called "export
feed") to be consumed by other systems.

Scrapy provides this functionality out of the box with the Feed Exports, which
allows you to generate a feed with the scraped items, using multiple
serialization formats and storage backends.

.. _topics-feed-format:

Serialization formats
=====================

For serializing the scraped data, the feed exports use the :ref:`Item exporters
<topics-exporters>` and these formats are supported out of the box:

 * :ref:`topics-feed-format-json`
 * :ref:`topics-feed-format-jsonlines`
 * :ref:`topics-feed-format-csv`
 * :ref:`topics-feed-format-xml`

But you can also extend the supported format through the
:setting:`FEED_EXPORTERS` setting.
 
.. _topics-feed-format-json:

JSON
----

 * :setting:`FEED_FORMAT`: ``json``
 * Exporter used: :class:`~scrapy.contrib.exporter.JsonItemExporter`
 * See :ref:`this warning <json-with-large-data>` if you're using JSON with large feeds

.. _topics-feed-format-jsonlines:

JSON lines
----------

 * :setting:`FEED_FORMAT`: ``jsonlines``
 * Exporter used: :class:`~scrapy.contrib.exporter.JsonLinesItemExporter`

.. _topics-feed-format-csv:

CSV
---

 * :setting:`FEED_FORMAT`: ``csv``
 * Exporter used: :class:`~scrapy.contrib.exporter.CsvItemExporter`

.. _topics-feed-format-xml:

XML
---

 * :setting:`FEED_FORMAT`: ``xml``
 * Exporter used: :class:`~scrapy.contrib.exporter.XmlItemExporter`

.. _topics-feed-format-pickle:

Pickle
------

 * :setting:`FEED_FORMAT`: ``pickle``
 * Exporter used: :class:`~scrapy.contrib.exporter.PickleItemExporter`

.. _topics-feed-format-marshal:

Marshal
-------

 * :setting:`FEED_FORMAT`: ``marshal``
 * Exporter used: :class:`~scrapy.contrib.exporter.MarshalItemExporter`


.. _topics-feed-storage:

Storages
========

When using the feed exports you define where to store the feed using a URI_
(through the :setting:`FEED_URI` setting). The feed exports supports multiple
storage backend types which are defined by the URI scheme.

The storages backends supported out of the box are:

 * :ref:`topics-feed-storage-fs`
 * :ref:`topics-feed-storage-ftp`
 * :ref:`topics-feed-storage-s3` (requires boto_)
 * :ref:`topics-feed-storage-stdout`

Some storage backends may be unavailable if the required external libraries are
not available. For example, the S3 backend is only available if the boto_
library is installed.


.. _topics-feed-uri-params:

Storage URI parameters
======================

The storage URI can also contain parameters that get replaced when the feed is
being created. These parameters are:

 * ``%(time)s`` - gets replaced by a timestamp when the feed is being created
 * ``%(name)s`` - gets replaced by the spider name

Any other named parameter gets replaced by the spider attribute of the same
name. For example, ``%(site_id)s`` would get replaced by the ``spider.site_id``
attribute the moment the feed is being created.

Here are some examples to illustrate:

 * Store in FTP using one directory per spider:

   * ``ftp://user:password@ftp.example.com/scraping/feeds/%(name)s/%(time)s.json``

 * Store in S3 using one directory per spider:

   * ``s3://mybucket/scraping/feeds/%(name)s/%(time)s.json``


.. _topics-feed-storage-backends:

Storage backends
================

.. _topics-feed-storage-fs:

Local filesystem
----------------

The feeds are stored in the local filesystem.

 * URI scheme: ``file``
 * Example URI: ``file:///tmp/export.csv``
 * Required external libraries: none

Note that for the local filesystem storage (only) you can omit the scheme if
you specify an absolute path like ``/tmp/export.csv``. This only works on Unix
systems though.

.. _topics-feed-storage-ftp:

FTP
---

The feeds are stored in a FTP server.

 * URI scheme: ``ftp``
 * Example URI: ``ftp://user:pass@ftp.example.com/path/to/export.csv``
 * Required external libraries: none

.. _topics-feed-storage-s3:

S3
--

The feeds are stored on `Amazon S3`_.

 * URI scheme: ``s3``
 * Example URIs:

   * ``s3://mybucket/path/to/export.csv``
   * ``s3://aws_key:aws_secret@mybucket/path/to/export.csv``

 * Required external libraries: `boto`_

The AWS credentials can be passed as user/password in the URI, or they can be
passed through the following settings:

 * :setting:`AWS_ACCESS_KEY_ID`
 * :setting:`AWS_SECRET_ACCESS_KEY`

.. _topics-feed-storage-stdout:

Standard output
---------------

The feeds are written to the standard output of the Scrapy process.

 * URI scheme: ``stdout``
 * Example URI: ``stdout:``
 * Required external libraries: none


Settings
========

These are the settings used for configuring the feed exports:

 * :setting:`FEED_URI` (mandatory)
 * :setting:`FEED_FORMAT`
 * :setting:`FEED_STORAGES`
 * :setting:`FEED_EXPORTERS`
 * :setting:`FEED_STORE_EMPTY`

.. currentmodule:: scrapy.contrib.feedexport

.. setting:: FEED_URI

FEED_URI
--------

Default: ``None``

The URI of the export feed. See :ref:`topics-feed-storage-backends` for
supported URI schemes.

This setting is required for enabling the feed exports.

.. setting:: FEED_FORMAT

FEED_FORMAT
-----------

The serialization format to be used for the feed. See
:ref:`topics-feed-format` for possible values.

.. setting:: FEED_STORE_EMPTY

FEED_STORE_EMPTY
----------------

Default: ``False``

Whether to export empty feeds (ie. feeds with no items).

.. setting:: FEED_STORAGES

FEED_STORAGES
-------------

Default:: ``{}``

A dict containing additional feed storage backends supported by your project.
The keys are URI schemes and the values are paths to storage classes.

.. setting:: FEED_STORAGES_BASE

FEED_STORAGES_BASE
------------------

Default:: 

    {
        '': 'scrapy.contrib.feedexport.FileFeedStorage',
        'file': 'scrapy.contrib.feedexport.FileFeedStorage',
        'stdout': 'scrapy.contrib.feedexport.StdoutFeedStorage',
        's3': 'scrapy.contrib.feedexport.S3FeedStorage',
        'ftp': 'scrapy.contrib.feedexport.FTPFeedStorage',
    }

A dict containing the built-in feed storage backends supported by Scrapy.

.. setting:: FEED_EXPORTERS

FEED_EXPORTERS
--------------

Default:: ``{}``

A dict containing additional exporters supported by your project. The keys are
URI schemes and the values are paths to :ref:`Item exporter <topics-exporters>`
classes.

.. setting:: FEED_EXPORTERS_BASE

FEED_EXPORTERS_BASE
-------------------

Default:: 

    FEED_EXPORTERS_BASE = {
        'json': 'scrapy.contrib.exporter.JsonItemExporter',
        'jsonlines': 'scrapy.contrib.exporter.JsonLinesItemExporter',
        'csv': 'scrapy.contrib.exporter.CsvItemExporter',
        'xml': 'scrapy.contrib.exporter.XmlItemExporter',
        'marshal': 'scrapy.contrib.exporter.MarshalItemExporter',
    }

A dict containing the built-in feed exporters supported by Scrapy.


.. _URI: http://en.wikipedia.org/wiki/Uniform_Resource_Identifier
.. _Amazon S3: http://aws.amazon.com/s3/
.. _boto: http://code.google.com/p/boto/

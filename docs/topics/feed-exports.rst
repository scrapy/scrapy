.. _topics-feed-exports:

============
Feed exports
============

One of the most frequently required features when implementing scrapers is
being able to store the scraped data properly and, quite often, that means
generating an "export file" with the scraped data (commonly called "export
feed") to be consumed by other systems.

Scrapy provides this functionality out of the box with the Feed Exports, which
allows you to generate feeds with the scraped items, using multiple
serialization formats and storage backends.

.. _topics-feed-format:

Serialization formats
=====================

For serializing the scraped data, the feed exports use the :ref:`Item exporters
<topics-exporters>`. These formats are supported out of the box:

-   :ref:`topics-feed-format-json`
-   :ref:`topics-feed-format-jsonlines`
-   :ref:`topics-feed-format-csv`
-   :ref:`topics-feed-format-xml`

But you can also extend the supported format through the
:setting:`FEED_EXPORTERS` setting.

.. _topics-feed-format-json:

JSON
----

-   Value for the ``format`` key in the :setting:`FEEDS` setting: ``json``

-   Exporter used: :class:`~scrapy.exporters.JsonItemExporter`

-   See :ref:`this warning <json-with-large-data>` if you're using JSON with
    large feeds.

.. _topics-feed-format-jsonlines:

JSON lines
----------

-   Value for the ``format`` key in the :setting:`FEEDS` setting: ``jsonlines``
-   Exporter used: :class:`~scrapy.exporters.JsonLinesItemExporter`

.. _topics-feed-format-csv:

CSV
---

-   Value for the ``format`` key in the :setting:`FEEDS` setting: ``csv``

-   Exporter used: :class:`~scrapy.exporters.CsvItemExporter`

-   To specify columns to export and their order use
    :setting:`FEED_EXPORT_FIELDS`. Other feed exporters can also use this
    option, but it is important for CSV because unlike many other export
    formats CSV uses a fixed header.

.. _topics-feed-format-xml:

XML
---

-   Value for the ``format`` key in the :setting:`FEEDS` setting: ``xml``
-   Exporter used: :class:`~scrapy.exporters.XmlItemExporter`

.. _topics-feed-format-pickle:

Pickle
------

-   Value for the ``format`` key in the :setting:`FEEDS` setting: ``pickle``
-   Exporter used: :class:`~scrapy.exporters.PickleItemExporter`

.. _topics-feed-format-marshal:

Marshal
-------

-   Value for the ``format`` key in the :setting:`FEEDS` setting: ``marshal``
-   Exporter used: :class:`~scrapy.exporters.MarshalItemExporter`


.. _topics-feed-storage:

Storages
========

When using the feed exports you define where to store the feed using one or multiple URIs_
(through the :setting:`FEEDS` setting). The feed exports supports multiple
storage backend types which are defined by the URI scheme.

The storages backends supported out of the box are:

-   :ref:`topics-feed-storage-fs`
-   :ref:`topics-feed-storage-ftp`
-   :ref:`topics-feed-storage-s3` (requires botocore_)
-   :ref:`topics-feed-storage-gcs` (requires `google-cloud-storage`_)
-   :ref:`topics-feed-storage-stdout`

Some storage backends may be unavailable if the required external libraries are
not available. For example, the S3 backend is only available if the botocore_
library is installed.


.. _topics-feed-uri-params:

Storage URI parameters
======================

The storage URI can also contain parameters that get replaced when the feed is
being created. These parameters are:

-   ``%(time)s`` - gets replaced by a timestamp when the feed is being created
-   ``%(name)s`` - gets replaced by the spider name

Any other named parameter gets replaced by the spider attribute of the same
name. For example, ``%(site_id)s`` would get replaced by the ``spider.site_id``
attribute the moment the feed is being created.

Here are some examples to illustrate:

-   Store in FTP using one directory per spider:

    -   ``ftp://user:password@ftp.example.com/scraping/feeds/%(name)s/%(time)s.json``

-   Store in S3 using one directory per spider:

    -   ``s3://mybucket/scraping/feeds/%(name)s/%(time)s.json``


.. _topics-feed-storage-backends:

Storage backends
================

.. _topics-feed-storage-fs:

Local filesystem
----------------

The feeds are stored in the local filesystem.

-   URI scheme: ``file``
-   Example URI: ``file:///tmp/export.csv``
-   Required external libraries: none

Note that for the local filesystem storage (only) you can omit the scheme if
you specify an absolute path like ``/tmp/export.csv``. This only works on Unix
systems though.

.. _topics-feed-storage-ftp:

FTP
---

The feeds are stored in a FTP server.

-   URI scheme: ``ftp``
-   Example URI: ``ftp://user:pass@ftp.example.com/path/to/export.csv``
-   Required external libraries: none

FTP supports two different connection modes: `active or passive
<https://stackoverflow.com/a/1699163>`_. Scrapy uses the passive connection
mode by default. To use the active connection mode instead, set the
:setting:`FEED_STORAGE_FTP_ACTIVE` setting to ``True``.

This storage backend uses :ref:`delayed file delivery <delayed-file-delivery>`.


.. _topics-feed-storage-s3:

S3
--

The feeds are stored on `Amazon S3`_.

-   URI scheme: ``s3``

-   Example URIs:

    -   ``s3://mybucket/path/to/export.csv``

    -   ``s3://aws_key:aws_secret@mybucket/path/to/export.csv``

-   Required external libraries: `botocore`_ >= 1.4.87

The AWS credentials can be passed as user/password in the URI, or they can be
passed through the following settings:

-   :setting:`AWS_ACCESS_KEY_ID`
-   :setting:`AWS_SECRET_ACCESS_KEY`

You can also define a custom ACL for exported feeds using this setting:

-   :setting:`FEED_STORAGE_S3_ACL`

This storage backend uses :ref:`delayed file delivery <delayed-file-delivery>`.


.. _topics-feed-storage-gcs:

Google Cloud Storage (GCS)
--------------------------

.. versionadded:: 2.3

The feeds are stored on `Google Cloud Storage`_.

-   URI scheme: ``gs``

-   Example URIs:

    -   ``gs://mybucket/path/to/export.csv``

-   Required external libraries: `google-cloud-storage`_.

For more information about authentication, please refer to `Google Cloud documentation <https://cloud.google.com/docs/authentication/production>`_.

You can set a *Project ID* and *Access Control List (ACL)* through the following settings:

-   :setting:`FEED_STORAGE_GCS_ACL`
-   :setting:`GCS_PROJECT_ID`

This storage backend uses :ref:`delayed file delivery <delayed-file-delivery>`.

.. _google-cloud-storage: https://cloud.google.com/storage/docs/reference/libraries#client-libraries-install-python


.. _topics-feed-storage-stdout:

Standard output
---------------

The feeds are written to the standard output of the Scrapy process.

-   URI scheme: ``stdout``
-   Example URI: ``stdout:``
-   Required external libraries: none


.. _delayed-file-delivery:

Delayed file delivery
---------------------

As indicated above, some of the described storage backends use delayed file
delivery.

These storage backends do not upload items to the feed URI as those items are
scraped. Instead, Scrapy writes items into a temporary local file, and only
once all the file contents have been written (i.e. at the end of the crawl) is
that file uploaded to the feed URI.

If you want item delivery to start earlier when using one of these storage
backends, use :setting:`FEED_EXPORT_BATCH_ITEM_COUNT` to split the output items
in multiple files, with the specified maximum item count per file. That way, as
soon as a file reaches the maximum item count, that file is delivered to the
feed URI, allowing item delivery to start way before the end of the crawl.


Settings
========

These are the settings used for configuring the feed exports:

-   :setting:`FEEDS` (mandatory)
-   :setting:`FEED_EXPORT_ENCODING`
-   :setting:`FEED_STORE_EMPTY`
-   :setting:`FEED_EXPORT_FIELDS`
-   :setting:`FEED_EXPORT_INDENT`
-   :setting:`FEED_STORAGES`
-   :setting:`FEED_STORAGE_FTP_ACTIVE`
-   :setting:`FEED_STORAGE_S3_ACL`
-   :setting:`FEED_EXPORTERS`
-   :setting:`FEED_EXPORT_BATCH_ITEM_COUNT`

.. currentmodule:: scrapy.extensions.feedexport

.. setting:: FEEDS

FEEDS
-----

.. versionadded:: 2.1

Default: ``{}``

A dictionary in which every key is a feed URI (or a :class:`pathlib.Path`
object) and each value is a nested dictionary containing configuration
parameters for the specific feed.

This setting is required for enabling the feed export feature.

See :ref:`topics-feed-storage-backends` for supported URI schemes.

For instance::

    {
        'items.json': {
            'format': 'json',
            'encoding': 'utf8',
            'store_empty': False,
            'fields': None,
            'indent': 4,
            'item_export_kwargs': {
               'export_empty_fields': True,
            },
        }, 
        '/home/user/documents/items.xml': {
            'format': 'xml',
            'fields': ['name', 'price'],
            'encoding': 'latin1',
            'indent': 8,
        },
        pathlib.Path('items.csv'): {
            'format': 'csv',
            'fields': ['price', 'name'],
        },
    }

.. _feed-options:

The following is a list of the accepted keys and the setting that is used
as a fallback value if that key is not provided for a specific feed definition:

-   ``format``: the :ref:`serialization format <topics-feed-format>`.

    This setting is mandatory, there is no fallback value.

-   ``batch_item_count``: falls back to
    :setting:`FEED_EXPORT_BATCH_ITEM_COUNT`.

    .. versionadded:: 2.3.0

-   ``encoding``: falls back to :setting:`FEED_EXPORT_ENCODING`.

-   ``fields``: falls back to :setting:`FEED_EXPORT_FIELDS`.

-   ``indent``: falls back to :setting:`FEED_EXPORT_INDENT`.

-   ``item_export_kwargs``: :class:`dict` with keyword arguments for the corresponding :ref:`item exporter class <topics-exporters>`.

    .. versionadded:: 2.4.0

-   ``overwrite``: whether to overwrite the file if it already exists
    (``True``) or append to its content (``False``).

    The default value depends on the :ref:`storage backend
    <topics-feed-storage-backends>`:

    -   :ref:`topics-feed-storage-fs`: ``False``

    -   :ref:`topics-feed-storage-ftp`: ``True``

        .. note:: Some FTP servers may not support appending to files (the
                  ``APPE`` FTP command).

    -   :ref:`topics-feed-storage-s3`: ``True`` (appending `is not supported
        <https://forums.aws.amazon.com/message.jspa?messageID=540395>`_)

    -   :ref:`topics-feed-storage-stdout`: ``False`` (overwriting is not supported)

    .. versionadded:: 2.4.0

-   ``store_empty``: falls back to :setting:`FEED_STORE_EMPTY`.

-   ``uri_params``: falls back to :setting:`FEED_URI_PARAMS`.


.. setting:: FEED_EXPORT_ENCODING

FEED_EXPORT_ENCODING
--------------------

Default: ``None``

The encoding to be used for the feed.

If unset or set to ``None`` (default) it uses UTF-8 for everything except JSON output,
which uses safe numeric encoding (``\uXXXX`` sequences) for historic reasons.

Use ``utf-8`` if you want UTF-8 for JSON too.

.. setting:: FEED_EXPORT_FIELDS

FEED_EXPORT_FIELDS
------------------

Default: ``None``

A list of fields to export, optional.
Example: ``FEED_EXPORT_FIELDS = ["foo", "bar", "baz"]``.

Use FEED_EXPORT_FIELDS option to define fields to export and their order.

When FEED_EXPORT_FIELDS is empty or None (default), Scrapy uses the fields
defined in :ref:`item objects <topics-items>` yielded by your spider.

If an exporter requires a fixed set of fields (this is the case for
:ref:`CSV <topics-feed-format-csv>` export format) and FEED_EXPORT_FIELDS
is empty or None, then Scrapy tries to infer field names from the
exported data - currently it uses field names from the first item.

.. setting:: FEED_EXPORT_INDENT

FEED_EXPORT_INDENT
------------------

Default: ``0``

Amount of spaces used to indent the output on each level. If ``FEED_EXPORT_INDENT``
is a non-negative integer, then array elements and object members will be pretty-printed
with that indent level. An indent level of ``0`` (the default), or negative,
will put each item on a new line. ``None`` selects the most compact representation.

Currently implemented only by :class:`~scrapy.exporters.JsonItemExporter`
and :class:`~scrapy.exporters.XmlItemExporter`, i.e. when you are exporting
to ``.json`` or ``.xml``.

.. setting:: FEED_STORE_EMPTY

FEED_STORE_EMPTY
----------------

Default: ``False``

Whether to export empty feeds (i.e. feeds with no items).

.. setting:: FEED_STORAGES

FEED_STORAGES
-------------

Default: ``{}``

A dict containing additional feed storage backends supported by your project.
The keys are URI schemes and the values are paths to storage classes.

.. setting:: FEED_STORAGE_FTP_ACTIVE

FEED_STORAGE_FTP_ACTIVE
-----------------------

Default: ``False``

Whether to use the active connection mode when exporting feeds to an FTP server
(``True``) or use the passive connection mode instead (``False``, default).

For information about FTP connection modes, see `What is the difference between
active and passive FTP? <https://stackoverflow.com/a/1699163>`_.

.. setting:: FEED_STORAGE_S3_ACL

FEED_STORAGE_S3_ACL
-------------------

Default: ``''`` (empty string)

A string containing a custom ACL for feeds exported to Amazon S3 by your project.

For a complete list of available values, access the `Canned ACL`_ section on Amazon S3 docs.

.. setting:: FEED_STORAGES_BASE

FEED_STORAGES_BASE
------------------

Default::

    {
        '': 'scrapy.extensions.feedexport.FileFeedStorage',
        'file': 'scrapy.extensions.feedexport.FileFeedStorage',
        'stdout': 'scrapy.extensions.feedexport.StdoutFeedStorage',
        's3': 'scrapy.extensions.feedexport.S3FeedStorage',
        'ftp': 'scrapy.extensions.feedexport.FTPFeedStorage',
    }

A dict containing the built-in feed storage backends supported by Scrapy. You
can disable any of these backends by assigning ``None`` to their URI scheme in
:setting:`FEED_STORAGES`. E.g., to disable the built-in FTP storage backend
(without replacement), place this in your ``settings.py``::

    FEED_STORAGES = {
        'ftp': None,
    }

.. setting:: FEED_EXPORTERS

FEED_EXPORTERS
--------------

Default: ``{}``

A dict containing additional exporters supported by your project. The keys are
serialization formats and the values are paths to :ref:`Item exporter
<topics-exporters>` classes.

.. setting:: FEED_EXPORTERS_BASE

FEED_EXPORTERS_BASE
-------------------
Default::

    {
        'json': 'scrapy.exporters.JsonItemExporter',
        'jsonlines': 'scrapy.exporters.JsonLinesItemExporter',
        'jl': 'scrapy.exporters.JsonLinesItemExporter',
        'csv': 'scrapy.exporters.CsvItemExporter',
        'xml': 'scrapy.exporters.XmlItemExporter',
        'marshal': 'scrapy.exporters.MarshalItemExporter',
        'pickle': 'scrapy.exporters.PickleItemExporter',
    }

A dict containing the built-in feed exporters supported by Scrapy. You can
disable any of these exporters by assigning ``None`` to their serialization
format in :setting:`FEED_EXPORTERS`. E.g., to disable the built-in CSV exporter
(without replacement), place this in your ``settings.py``::

    FEED_EXPORTERS = {
        'csv': None,
    }


.. setting:: FEED_EXPORT_BATCH_ITEM_COUNT

FEED_EXPORT_BATCH_ITEM_COUNT
----------------------------

.. versionadded:: 2.3.0

Default: ``0``

If assigned an integer number higher than ``0``, Scrapy generates multiple output files
storing up to the specified number of items in each output file.

When generating multiple output files, you must use at least one of the following
placeholders in the feed URI to indicate how the different output file names are
generated:

* ``%(batch_time)s`` - gets replaced by a timestamp when the feed is being created
  (e.g. ``2020-03-28T14-45-08.237134``)

* ``%(batch_id)d`` - gets replaced by the 1-based sequence number of the batch.

  Use :ref:`printf-style string formatting <python:old-string-formatting>` to
  alter the number format. For example, to make the batch ID a 5-digit
  number by introducing leading zeroes as needed, use ``%(batch_id)05d``
  (e.g. ``3`` becomes ``00003``, ``123`` becomes ``00123``).

For instance, if your settings include::

    FEED_EXPORT_BATCH_ITEM_COUNT = 100

And your :command:`crawl` command line is::

    scrapy crawl spidername -o "dirname/%(batch_id)d-filename%(batch_time)s.json"

The command line above can generate a directory tree like::

    ->projectname
    -->dirname
    --->1-filename2020-03-28T14-45-08.237134.json
    --->2-filename2020-03-28T14-45-09.148903.json
    --->3-filename2020-03-28T14-45-10.046092.json

Where the first and second files contain exactly 100 items. The last one contains
100 items or fewer.


.. setting:: FEED_URI_PARAMS

FEED_URI_PARAMS
---------------

Default: ``None``

A string with the import path of a function to set the parameters to apply with
:ref:`printf-style string formatting <python:old-string-formatting>` to the
feed URI.

The function signature should be as follows:

.. function:: uri_params(params, spider)

   Return a :class:`dict` of key-value pairs to apply to the feed URI using
   :ref:`printf-style string formatting <python:old-string-formatting>`.

   :param params: default key-value pairs

        Specifically:

        -   ``batch_id``: ID of the file batch. See
            :setting:`FEED_EXPORT_BATCH_ITEM_COUNT`.

            If :setting:`FEED_EXPORT_BATCH_ITEM_COUNT` is ``0``, ``batch_id``
            is always ``1``.

            .. versionadded:: 2.3.0

        -   ``batch_time``: UTC date and time, in ISO format with ``:``
            replaced with ``-``.

            See :setting:`FEED_EXPORT_BATCH_ITEM_COUNT`.

            .. versionadded:: 2.3.0

        -   ``time``: ``batch_time``, with microseconds set to ``0``.
   :type params: dict

   :param spider: source spider of the feed items
   :type spider: scrapy.spiders.Spider

For example, to include the :attr:`name <scrapy.spiders.Spider.name>` of the
source spider in the feed URI:

#.  Define the following function somewhere in your project::

        # myproject/utils.py
        def uri_params(params, spider):
            return {**params, 'spider_name': spider.name}

#.  Point :setting:`FEED_URI_PARAMS` to that function in your settings::

        # myproject/settings.py
        FEED_URI_PARAMS = 'myproject.utils.uri_params'

#.  Use ``%(spider_name)s`` in your feed URI::

        scrapy crawl <spider_name> -o "%(spider_name)s.jl"


.. _URIs: https://en.wikipedia.org/wiki/Uniform_Resource_Identifier
.. _Amazon S3: https://aws.amazon.com/s3/
.. _botocore: https://github.com/boto/botocore
.. _Canned ACL: https://docs.aws.amazon.com/AmazonS3/latest/dev/acl-overview.html#canned-acl
.. _Google Cloud Storage: https://cloud.google.com/storage/

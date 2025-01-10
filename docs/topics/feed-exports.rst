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

This page provides detailed documentation for all feed export features. If you
are looking for a step-by-step guide, check out `Zyte’s export guides`_.

.. _Zyte’s export guides: https://docs.zyte.com/web-scraping/guides/export/index.html#exporting-scraped-data

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

-   To specify columns to export, their order and their column names, use
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
-   :ref:`topics-feed-storage-s3` (requires boto3_)
-   :ref:`topics-feed-storage-gcs` (requires `google-cloud-storage`_)
-   :ref:`topics-feed-storage-stdout`

Some storage backends may be unavailable if the required external libraries are
not available. For example, the S3 backend is only available if the boto3_
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

.. note:: :ref:`Spider arguments <spiderargs>` become spider attributes, hence
          they can also be used as storage URI parameters.


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
you specify an absolute path like ``/tmp/export.csv`` (Unix systems only).
Alternatively you can also use a :class:`pathlib.Path` object.

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

The default value for the ``overwrite`` key in the :setting:`FEEDS` for this 
storage backend is: ``True``.

.. caution:: The value ``True`` in ``overwrite`` will cause you to lose the
     previous version of your data.

This storage backend uses :ref:`delayed file delivery <delayed-file-delivery>`.


.. _topics-feed-storage-s3:

S3
--

The feeds are stored on `Amazon S3`_.

-   URI scheme: ``s3``

-   Example URIs:

    -   ``s3://mybucket/path/to/export.csv``

    -   ``s3://aws_key:aws_secret@mybucket/path/to/export.csv``

-   Required external libraries: `boto3`_ >= 1.20.0

The AWS credentials can be passed as user/password in the URI, or they can be
passed through the following settings:

-   :setting:`AWS_ACCESS_KEY_ID`
-   :setting:`AWS_SECRET_ACCESS_KEY`
-   :setting:`AWS_SESSION_TOKEN` (only needed for `temporary security credentials`_)

.. _temporary security credentials: https://docs.aws.amazon.com/IAM/latest/UserGuide/security-creds.html

You can also define a custom ACL, custom endpoint, and region name for exported
feeds using these settings:

-   :setting:`FEED_STORAGE_S3_ACL`
-   :setting:`AWS_ENDPOINT_URL`
-   :setting:`AWS_REGION_NAME`

The default value for the ``overwrite`` key in the :setting:`FEEDS` for this 
storage backend is: ``True``.

.. caution:: The value ``True`` in ``overwrite`` will cause you to lose the
     previous version of your data.

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

For more information about authentication, please refer to `Google Cloud documentation <https://cloud.google.com/docs/authentication>`_.

You can set a *Project ID* and *Access Control List (ACL)* through the following settings:

-   :setting:`FEED_STORAGE_GCS_ACL`
-   :setting:`GCS_PROJECT_ID`

The default value for the ``overwrite`` key in the :setting:`FEEDS` for this 
storage backend is: ``True``.

.. caution:: The value ``True`` in ``overwrite`` will cause you to lose the
     previous version of your data.

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


.. _item-filter:

Item filtering
==============

.. versionadded:: 2.6.0

You can filter items that you want to allow for a particular feed by using the
``item_classes`` option in :ref:`feeds options <feed-options>`. Only items of
the specified types will be added to the feed.

The ``item_classes`` option is implemented by the :class:`~scrapy.extensions.feedexport.ItemFilter`
class, which is the default value of the ``item_filter`` :ref:`feed option <feed-options>`.

You can create your own custom filtering class by implementing :class:`~scrapy.extensions.feedexport.ItemFilter`'s
method ``accepts`` and taking ``feed_options`` as an argument.

For instance:

.. code-block:: python

    class MyCustomFilter:
        def __init__(self, feed_options):
            self.feed_options = feed_options

        def accepts(self, item):
            if "field1" in item and item["field1"] == "expected_data":
                return True
            return False


You can assign your custom filtering class to the ``item_filter`` :ref:`option of a feed <feed-options>`.
See :setting:`FEEDS` for examples.

ItemFilter
----------

.. autoclass:: scrapy.extensions.feedexport.ItemFilter
   :members:


.. _post-processing:

Post-Processing
===============

.. versionadded:: 2.6.0

Scrapy provides an option to activate plugins to post-process feeds before they are exported
to feed storages. In addition to using :ref:`builtin plugins <builtin-plugins>`, you
can create your own :ref:`plugins <custom-plugins>`.

These plugins can be activated through the ``postprocessing`` option of a feed.
The option must be passed a list of post-processing plugins in the order you want
the feed to be processed. These plugins can be declared either as an import string
or with the imported class of the plugin. Parameters to plugins can be passed
through the feed options. See :ref:`feed options <feed-options>` for examples.

.. _builtin-plugins:

Built-in Plugins
----------------

.. autoclass:: scrapy.extensions.postprocessing.GzipPlugin

.. autoclass:: scrapy.extensions.postprocessing.LZMAPlugin

.. autoclass:: scrapy.extensions.postprocessing.Bz2Plugin

.. _custom-plugins:

Custom Plugins
--------------

Each plugin is a class that must implement the following methods:

.. method:: __init__(self, file, feed_options)

    Initialize the plugin.

    :param file: file-like object having at least the `write`, `tell` and `close` methods implemented

    :param feed_options: feed-specific :ref:`options <feed-options>`
    :type feed_options: :class:`dict`

.. method:: write(self, data)

   Process and write `data` (:class:`bytes` or :class:`memoryview`) into the plugin's target file.
   It must return number of bytes written.

.. method:: close(self)

    Clean up the plugin.

    For example, you might want to close a file wrapper that you might have
    used to compress data written into the file received in the ``__init__``
    method.

    .. warning:: Do not close the file from the ``__init__`` method.

To pass a parameter to your plugin, use :ref:`feed options <feed-options>`. You
can then access those parameters from the ``__init__`` method of your plugin.


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
            'item_classes': [MyItemClass1, 'myproject.items.MyItemClass2'],
            'fields': None,
            'indent': 4,
            'item_export_kwargs': {
               'export_empty_fields': True,
            },
        },
        '/home/user/documents/items.xml': {
            'format': 'xml',
            'fields': ['name', 'price'],
            'item_filter': MyCustomFilter1,
            'encoding': 'latin1',
            'indent': 8,
        },
        pathlib.Path('items.csv.gz'): {
            'format': 'csv',
            'fields': ['price', 'name'],
            'item_filter': 'myproject.filters.MyCustomFilter2',
            'postprocessing': [MyPlugin1, 'scrapy.extensions.postprocessing.GzipPlugin'],
            'gzip_compresslevel': 5,
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

-   ``item_classes``: list of :ref:`item classes <topics-items>` to export.

    If undefined or empty, all items are exported.

    .. versionadded:: 2.6.0

-   ``item_filter``: a :ref:`filter class <item-filter>` to filter items to export.

    :class:`~scrapy.extensions.feedexport.ItemFilter` is used be default.

    .. versionadded:: 2.6.0

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

    -   :ref:`topics-feed-storage-s3`: ``True`` (appending is not supported)

    -   :ref:`topics-feed-storage-gcs`: ``True`` (appending is not supported)

    -   :ref:`topics-feed-storage-stdout`: ``False`` (overwriting is not supported)

    .. versionadded:: 2.4.0

-   ``store_empty``: falls back to :setting:`FEED_STORE_EMPTY`.

-   ``uri_params``: falls back to :setting:`FEED_URI_PARAMS`.

-   ``postprocessing``: list of :ref:`plugins <post-processing>` to use for post-processing.

    The plugins will be used in the order of the list passed.

    .. versionadded:: 2.6.0

.. setting:: FEED_EXPORT_ENCODING

FEED_EXPORT_ENCODING
--------------------

Default: ``None``

The encoding to be used for the feed.

If unset or set to ``None`` (default) it uses UTF-8 for everything except JSON output,
which uses safe numeric encoding (``\uXXXX`` sequences) for historic reasons.

Use ``utf-8`` if you want UTF-8 for JSON too.

.. versionchanged:: 2.8
   The :command:`startproject` command now sets this setting to
   ``utf-8`` in the generated ``settings.py`` file.

.. setting:: FEED_EXPORT_FIELDS

FEED_EXPORT_FIELDS
------------------

Default: ``None``

Use the ``FEED_EXPORT_FIELDS`` setting to define the fields to export, their
order and their output names. See :attr:`BaseItemExporter.fields_to_export
<scrapy.exporters.BaseItemExporter.fields_to_export>` for more information.

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

Default: ``True``

Whether to export empty feeds (i.e. feeds with no items).
If ``False``, and there are no items to export, no new files are created and 
existing files are not modified, even if the :ref:`overwrite feed option 
<feed-options>` is enabled.

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

Default:

.. code-block:: python

    {
        "": "scrapy.extensions.feedexport.FileFeedStorage",
        "file": "scrapy.extensions.feedexport.FileFeedStorage",
        "stdout": "scrapy.extensions.feedexport.StdoutFeedStorage",
        "s3": "scrapy.extensions.feedexport.S3FeedStorage",
        "ftp": "scrapy.extensions.feedexport.FTPFeedStorage",
    }

A dict containing the built-in feed storage backends supported by Scrapy. You
can disable any of these backends by assigning ``None`` to their URI scheme in
:setting:`FEED_STORAGES`. E.g., to disable the built-in FTP storage backend
(without replacement), place this in your ``settings.py``:

.. code-block:: python

    FEED_STORAGES = {
        "ftp": None,
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
Default:

.. code-block:: python

    {
        "json": "scrapy.exporters.JsonItemExporter",
        "jsonlines": "scrapy.exporters.JsonLinesItemExporter",
        "jsonl": "scrapy.exporters.JsonLinesItemExporter",
        "jl": "scrapy.exporters.JsonLinesItemExporter",
        "csv": "scrapy.exporters.CsvItemExporter",
        "xml": "scrapy.exporters.XmlItemExporter",
        "marshal": "scrapy.exporters.MarshalItemExporter",
        "pickle": "scrapy.exporters.PickleItemExporter",
    }

A dict containing the built-in feed exporters supported by Scrapy. You can
disable any of these exporters by assigning ``None`` to their serialization
format in :setting:`FEED_EXPORTERS`. E.g., to disable the built-in CSV exporter
(without replacement), place this in your ``settings.py``:

.. code-block:: python

    FEED_EXPORTERS = {
        "csv": None,
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

For instance, if your settings include:

.. code-block:: python

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
   :type spider: scrapy.Spider

   .. caution:: The function should return a new dictionary, modifying
                the received ``params`` in-place is deprecated.

For example, to include the :attr:`name <scrapy.Spider.name>` of the
source spider in the feed URI:

#.  Define the following function somewhere in your project:

    .. code-block:: python

        # myproject/utils.py
        def uri_params(params, spider):
            return {**params, "spider_name": spider.name}

#.  Point :setting:`FEED_URI_PARAMS` to that function in your settings:

    .. code-block:: python

        # myproject/settings.py
        FEED_URI_PARAMS = "myproject.utils.uri_params"

#.  Use ``%(spider_name)s`` in your feed URI::

        scrapy crawl <spider_name> -o "%(spider_name)s.jsonl"


.. _URIs: https://en.wikipedia.org/wiki/Uniform_Resource_Identifier
.. _Amazon S3: https://aws.amazon.com/s3/
.. _boto3: https://github.com/boto/boto3
.. _Canned ACL: https://docs.aws.amazon.com/AmazonS3/latest/userguide/acl-overview.html#canned-acl
.. _Google Cloud Storage: https://cloud.google.com/storage/

.. _topics-item-pipeline:

=============
Item Pipeline
=============

.. module:: scrapy.contrib.pipeline
   :synopsis: Item Pipeline manager and built-in pipelines

After an item has been scraped by a spider it is sent to the Item Pipeline
which process it through several components that are executed sequentially.

Item pipeline are usually implemented on each project. Typical usage for item
pipelines are:

* HTML cleansing
* validation
* persistence (storing the scraped item)


Writing your own item pipeline
==============================

Writing your own item pipeline is easy. Each item pipeline component is a
single Python class that must define the following method:

.. method:: process_item(domain, item)

``domain`` is a string with the domain of the spider which scraped the item

``item`` is a :class:`~scrapy.item.Item` with the item scraped

This method is called for every item pipeline component and must either return
a :class:`~scrapy.item.Item` (or any descendant class) object or raise a
:exc:`~scrapy.core.exceptions.DropItem` exception. Dropped items are no longer
processed by further pipeline components.


Item pipeline example
=====================

Let's take a look at following hypothetic pipeline that adjusts the ``price``
attribute for those items that do not include VAT (``price_excludes_vat``
attribute), and drops those items which don't contain a price::

    from scrapy.core.exceptions import DropItem

    class PricePipeline(object):

        vat_factor = 1.15

        def process_item(self, domain, item):
            if item['price']:
                if item['price_excludes_vat']:
                    item['price'] = item['price'] * self.vat_factor
                return item
            else:
                raise DropItem("Missing price in %s" % item)


Item pipeline example with resources per domain
===============================================

Sometimes you need to keep resources about the items processed grouped per
domain, and delete those resource when a domain finish.

An example is a filter that looks for duplicate items, and drops those items
that were already processed. Let say that our items has an unique id, but our
spider returns multiples items with the same id::


    from scrapy.xlib.pydispatch import dispatcher
    from scrapy.core import signals
    from scrapy.core.exceptions import DropItem

    class DuplicatesPipeline(object):
        def __init__(self):
            self.domaininfo = {}
            dispatcher.connect(self.domain_opened, signals.domain_opened)
            dispatcher.connect(self.domain_closed, signals.domain_closed)

        def domain_opened(self, domain):
            self.duplicates[domain] = set()

        def domain_closed(self, domain):
            del self.duplicates[domain]

        def process_item(self, domain, item):
            if item.id in self.duplicates[domain]:
                raise DropItem("Duplicate item found: %s" % item)
            else:
                self.duplicates[domain].add(item.id)
                return item

Built-in Item Pipelines reference
=================================

Here is a list of item pipelines bundled with Scrapy.

File Export Pipeline
--------------------

.. module:: scrapy.contrib.pipeline.fileexport

.. class:: FileExportPipeline

This pipeline exports all scraped items into a file, using different formats.

It is simple but convenient wrapper to use :doc:`Item Exporters <exporters>` as
:ref:`Item Pipelines <topics-item-pipeline>`. If you need more custom/advanced
functionality you can write your own pipeline or subclass the :doc:`Item
Exporters <exporters>` .

It supports the following settings:

* :setting:`EXPORT_FORMAT` (mandatory)
* :setting:`EXPORT_FILE` (mandatory)
* :setting:`EXPORT_FIELDS`
* :setting:`EXPORT_EMPTY`
* :setting:`EXPORT_ENCODING`

If any mandatory setting is not set, this pipeline will be automatically
disabled.

File Export Pipeline examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Here are some usage examples of the File Export Pipeline.

To export all scraped items into a XML file::

    EXPORT_FORMAT = 'xml'
    EXPORT_FILE = 'scraped_items.xml'

To export all scraped items into a CSV file (without a headers line)::

    EXPORT_FORMAT = 'csv'
    EXPORT_FILE = 'scraped_items.csv'

To export all scraped items into a CSV file (with a headers line)::

    EXPORT_FORMAT = 'csv_headers'
    EXPORT_FILE = 'scraped_items_with_headers.csv'
    EXPORT_FILEDS = ['name', 'price', 'description']

File Export Pipeline settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. currentmodule:: scrapy.contrib.exporter

.. setting:: EXPORT_FORMAT

EXPORT_FORMAT
^^^^^^^^^^^^^

The format to use for exporting. Here is a list of all available formats. Click
on the respective Item Exporter to get more info.

* ``xml``: uses a :class:`XmlItemExporter`

* ``csv``: uses a :class:`CsvItemExporter`

* ``csv_headers``: uses a :class:`CsvItemExporter` with a the column headers on
  the first line. This format requires you to specify the fields to export
  using the :setting:`EXPORT_FIELDS` setting.

* ``jsonlines``: uses a :class:`jsonlines.JsonLinesItemExporter`

* ``pickle``: uses a :class:`PickleItemExporter`

* ``pprint``: uses a :class:`PprintItemExporter`

This setting is mandatory in order to use the File Export Pipeline.

.. setting:: EXPORT_FILE

EXPORT_FILE
^^^^^^^^^^^

The name of the file where the items will be exported. This setting is
mandatory in order to use the File Export Pipeline.

.. setting:: EXPORT_FIELDS

EXPORT_FIELDS
^^^^^^^^^^^^^

Default: ``None``

The name of the item fields that will be exported. This will be use for the
:attr:`~BaseItemExporter.fields_to_export` Item Exporter attribute. If
``None``, all fields will be exported.

.. setting:: EXPORT_EMPTY

EXPORT_EMPTY
^^^^^^^^^^^^

Whether to export empty (non populated) fields. This will be used for the
:attr:`~BaseItemExporter.export_empty_fields` Item Exporter attribute.

.. setting:: EXPORT_ENCODING

EXPORT_ENCODING
^^^^^^^^^^^^^^^

The encoding to use for exporting. Ths will be used for the
:attr:`~BaseItemExporter.encoding` Item Exporter attribute.


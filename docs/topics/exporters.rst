.. _topics-exporters:

==============
Item Exporters
==============

.. module:: scrapy.contrib.exporter
   :synopsis: Item Exporters

Once you have scraped your Items, you often want to persist or export those
items, to use the data in some other application. That is, after all, the whole
purpose of the scraping process.

For this purpose Scrapy provides a collection of Item Exporters for different
output formats, such as XML, CSV or JSON.

Using Item Exporters
====================

If you are in a hurry, and just want to use an Item Exporter to output scraped
data see the :ref:`topics-feed-exports`. Otherwise, if you want to know how
Item Exporters work or need more custom functionality (not covered by the
default exports), continue reading below.

In order to use an Item Exporter, you  must instantiate it with its required
args. Each Item Exporter requires different arguments, so check each exporter
documentation to be sure, in :ref:`topics-exporters-reference`. After you have
instantiated your exporter, you have to:

1. call the method :meth:`~BaseItemExporter.start_exporting` in order to
signal the beginning of the exporting process

2. call the :meth:`~BaseItemExporter.export_item` method for each item you want
to export

3. and finally call the :meth:`~BaseItemExporter.finish_exporting` to signal
the end of the exporting process

Here you can see an :doc:`Item Pipeline <item-pipeline>` which uses an Item
Exporter to export scraped items to different files, one per spider::

   from scrapy import signals
   from scrapy.contrib.exporter import XmlItemExporter

   class XmlExportPipeline(object):

       def __init__(self):
           self.files = {}

        @classmethod
        def from_crawler(cls, crawler):
            pipeline = cls()
            crawler.signals.connect(pipeline.spider_opened, signals.spider_opened)
            crawler.signals.connect(pipeline.spider_closed, signals.spider_closed)
            return pipeline

       def spider_opened(self, spider):
           file = open('%s_products.xml' % spider.name, 'w+b')
           self.files[spider] = file
           self.exporter = XmlItemExporter(file)
           self.exporter.start_exporting()

       def spider_closed(self, spider):
           self.exporter.finish_exporting()
           file = self.files.pop(spider)
           file.close()

       def process_item(self, item, spider):
           self.exporter.export_item(item)
           return item


.. _topics-exporters-field-serialization:

Serialization of item fields
============================

By default, the field values are passed unmodified to the underlying
serialization library, and the decision of how to serialize them is delegated
to each particular serialization library.

However, you can customize how each field value is serialized *before it is
passed to the serialization library*.

There are two ways to customize how a field will be serialized, which are
described next.

.. _topics-exporters-serializers:

1. Declaring a serializer in the field
--------------------------------------

You can declare a serializer in the :ref:`field metadata
<topics-items-fields>`. The serializer must be a callable which receives a
value and returns its serialized form.

Example::

    import scrapy

    def serialize_price(value):
        return '$ %s' % str(value)

    class Product(scrapy.Item):
        name = scrapy.Field()
        price = scrapy.Field(serializer=serialize_price)


2. Overriding the serialize_field() method
------------------------------------------

You can also override the :meth:`~BaseItemExporter.serialize_field()` method to
customize how your field value will be exported.

Make sure you call the base class :meth:`~BaseItemExporter.serialize_field()` method
after your custom code.

Example::

      from scrapy.contrib.exporter import XmlItemExporter

      class ProductXmlExporter(XmlItemExporter):

          def serialize_field(self, field, name, value):
              if field == 'price':
                  return '$ %s' % str(value)
              return super(Product, self).serialize_field(field, name, value)

.. _topics-exporters-reference:

Built-in Item Exporters reference
=================================

Here is a list of the Item Exporters bundled with Scrapy. Some of them contain
output examples, which assume you're exporting these two items::

    Item(name='Color TV', price='1200')
    Item(name='DVD player', price='200')

BaseItemExporter
----------------

.. class:: BaseItemExporter(fields_to_export=None, export_empty_fields=False, encoding='utf-8')

   This is the (abstract) base class for all Item Exporters. It provides
   support for common features used by all (concrete) Item Exporters, such as
   defining what fields to export, whether to export empty fields, or which
   encoding to use.

   These features can be configured through the constructor arguments which
   populate their respective instance attributes: :attr:`fields_to_export`,
   :attr:`export_empty_fields`, :attr:`encoding`.

   .. method:: export_item(item)

      Exports the given item. This method must be implemented in subclasses.

   .. method:: serialize_field(field, name, value)

      Return the serialized value for the given field. You can override this
      method (in your custom Item Exporters) if you want to control how a
      particular field or value will be serialized/exported.

      By default, this method looks for a serializer :ref:`declared in the item
      field <topics-exporters-serializers>` and returns the result of applying
      that serializer to the value. If no serializer is found, it returns the
      value unchanged except for ``unicode`` values which are encoded to
      ``str`` using the encoding declared in the :attr:`encoding` attribute.

      :param field: the field being serialized
      :type field: :class:`~scrapy.item.Field` object

      :param name: the name of the field being serialized
      :type name: str

      :param value: the value being serialized

   .. method:: start_exporting()

      Signal the beginning of the exporting process. Some exporters may use
      this to generate some required header (for example, the
      :class:`XmlItemExporter`). You must call this method before exporting any
      items.

   .. method:: finish_exporting()

      Signal the end of the exporting process. Some exporters may use this to
      generate some required footer (for example, the
      :class:`XmlItemExporter`). You must always call this method after you
      have no more items to export.

   .. attribute:: fields_to_export

      A list with the name of the fields that will be exported, or None if you
      want to export all fields. Defaults to None.

      Some exporters (like :class:`CsvItemExporter`) respect the order of the
      fields defined in this attribute.

   .. attribute:: export_empty_fields

      Whether to include empty/unpopulated item fields in the exported data.
      Defaults to ``False``. Some exporters (like :class:`CsvItemExporter`)
      ignore this attribute and always export all empty fields.

   .. attribute:: encoding

      The encoding that will be used to encode unicode values. This only
      affects unicode values (which are always serialized to str using this
      encoding). Other value types are passed unchanged to the specific
      serialization library.

.. highlight:: none

XmlItemExporter
---------------

.. class:: XmlItemExporter(file, item_element='item', root_element='items', \**kwargs)

   Exports Items in XML format to the specified file object.

   :param file: the file-like object to use for exporting the data.

   :param root_element: The name of root element in the exported XML.
   :type root_element: str

   :param item_element: The name of each item element in the exported XML.
   :type item_element: str

   The additional keyword arguments of this constructor are passed to the
   :class:`BaseItemExporter` constructor.

   A typical output of this exporter would be::

       <?xml version="1.0" encoding="utf-8"?>
       <items>
         <item>
           <name>Color TV</name>
           <price>1200</price>
        </item>
         <item>
           <name>DVD player</name>
           <price>200</price>
        </item>
       </items>

   Unless overridden in the :meth:`serialize_field` method, multi-valued fields are
   exported by serializing each value inside a ``<value>`` element. This is for
   convenience, as multi-valued fields are very common.

   For example, the item::

        Item(name=['John', 'Doe'], age='23')

   Would be serialized as::

       <?xml version="1.0" encoding="utf-8"?>
       <items>
         <item>
           <name>
             <value>John</value>
             <value>Doe</value>
           </name>
           <age>23</age>
         </item>
       </items>

CsvItemExporter
---------------

.. class:: CsvItemExporter(file, include_headers_line=True, join_multivalued=',', \**kwargs)

   Exports Items in CSV format to the given file-like object. If the
   :attr:`fields_to_export` attribute is set, it will be used to define the
   CSV columns and their order. The :attr:`export_empty_fields` attribute has
   no effect on this exporter.

   :param file: the file-like object to use for exporting the data.

   :param include_headers_line: If enabled, makes the exporter output a header
      line with the field names taken from
      :attr:`BaseItemExporter.fields_to_export` or the first exported item fields.
   :type include_headers_line: boolean

   :param join_multivalued: The char (or chars) that will be used for joining
      multi-valued fields, if found.
   :type include_headers_line: str

   The additional keyword arguments of this constructor are passed to the
   :class:`BaseItemExporter` constructor, and the leftover arguments to the
   `csv.writer`_ constructor, so you can use any `csv.writer` constructor
   argument to customize this exporter.

   A typical output of this exporter would be::

      product,price
      Color TV,1200
      DVD player,200

.. _csv.writer: http://docs.python.org/library/csv.html#csv.writer

PickleItemExporter
------------------

.. class:: PickleItemExporter(file, protocol=0, \**kwargs)

   Exports Items in pickle format to the given file-like object.

   :param file: the file-like object to use for exporting the data.

   :param protocol: The pickle protocol to use.
   :type protocol: int

   For more information, refer to the `pickle module documentation`_.

   The additional keyword arguments of this constructor are passed to the
   :class:`BaseItemExporter` constructor.

   Pickle isn't a human readable format, so no output examples are provided.

.. _pickle module documentation: http://docs.python.org/library/pickle.html

PprintItemExporter
------------------

.. class:: PprintItemExporter(file, \**kwargs)

   Exports Items in pretty print format to the specified file object.

   :param file: the file-like object to use for exporting the data.

   The additional keyword arguments of this constructor are passed to the
   :class:`BaseItemExporter` constructor.

   A typical output of this exporter would be::

        {'name': 'Color TV', 'price': '1200'}
        {'name': 'DVD player', 'price': '200'}

   Longer lines (when present) are pretty-formatted.

JsonItemExporter
----------------

.. class:: JsonItemExporter(file, \**kwargs)

   Exports Items in JSON format to the specified file-like object, writing all
   objects as a list of objects. The additional constructor arguments are
   passed to the :class:`BaseItemExporter` constructor, and the leftover
   arguments to the `JSONEncoder`_ constructor, so you can use any
   `JSONEncoder`_ constructor argument to customize this exporter.

   :param file: the file-like object to use for exporting the data.

   A typical output of this exporter would be::

        [{"name": "Color TV", "price": "1200"},
        {"name": "DVD player", "price": "200"}]

   .. _json-with-large-data:

   .. warning:: JSON is very simple and flexible serialization format, but it
      doesn't scale well for large amounts of data since incremental (aka.
      stream-mode) parsing is not well supported (if at all) among JSON parsers
      (on any language), and most of them just parse the entire object in
      memory. If you want the power and simplicity of JSON with a more
      stream-friendly format, consider using :class:`JsonLinesItemExporter`
      instead, or splitting the output in multiple chunks.

.. _JSONEncoder: http://docs.python.org/library/json.html#json.JSONEncoder

JsonLinesItemExporter
---------------------

.. class:: JsonLinesItemExporter(file, \**kwargs)

   Exports Items in JSON format to the specified file-like object, writing one
   JSON-encoded item per line. The additional constructor arguments are passed
   to the :class:`BaseItemExporter` constructor, and the leftover arguments to
   the `JSONEncoder`_ constructor, so you can use any `JSONEncoder`_
   constructor argument to customize this exporter.

   :param file: the file-like object to use for exporting the data.

   A typical output of this exporter would be::

        {"name": "Color TV", "price": "1200"}
        {"name": "DVD player", "price": "200"}

   Unlike the one produced by :class:`JsonItemExporter`, the format produced by
   this exporter is well suited for serializing large amounts of data.

.. _JSONEncoder: http://docs.python.org/library/json.html#json.JSONEncoder

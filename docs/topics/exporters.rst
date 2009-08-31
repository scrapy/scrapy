.. _topics-exporters:

==============
Item Exporters
==============

.. module:: scrapy.contrib.exporter
   :synopsis: Item Exporters

Once you have scraped your Items, one of the most common tasks to perform on
those items is to export them, to use the data in some other application. That
is, after all, the whole purpose of the scraping process.

To help in this purpose Scrapy provides a collectioon of Item Exporters for
different output formats, such as XML, CSV or JSON.

Using Item Exporters
====================

In order to use a Item Exporter, you  must instantiate it with its required
args.  Different exporters require different args, so check each exporter
documentation to be sure, in :ref:`topics-exporters-reference`. After you have
instantiated you exporter, you call the method
:meth:`~BaseItemExporter.start_exporting` in order to initialize the exporting
proces, then you call :meth:`~BaseItemExporter.export_item` method for each
item you want to export, and finally call
:meth:`~BaseItemExporter.finish_exporting` to finalize the exporting process.

Here you can see a typical Item Exporter usage in an :ref:`Item Pipeline
<topics-item-pipeline>`::

   from scrapy.xlib.pydispatch import dispatcher
   from scrapy.contrib.exporter import XmlItemExporter

   class XmlExportPipeline(object):

       def __init__(self):
           dispatcher.connect(self.domain_opened, signals.domain_opened) 
           dispatcher.connect(self.domain_closed, signals.domain_closed)

       def domain_opened(self, domain):
           self.file = open('%s_products.xml' % domain)
           self.exporter = XmlItemExporter(self.file)
           self.exporter.start_exporting()

       def domain_closed(self, domain):
           self.exporter.finish_exporting()
           self.file.close()

       def process_item(self, domain, item):
           self.exporter.export_item(item)
           return item


.. _topics-exporters-field-serialization:

Serialization of item fields
============================

By default the field values are passed unmodified to the underlying
serialization library, and the decision of how to serialize them is delegated
to each particular serialization library.

However, you can customize how each field value is serialized, prior to passing
it to the serialization library, if the exporter supports it.

There are ways to customize how a field will be serialized, which are described
next.

.. _topics-exporters-serializers:

1. Declaring a serializer in the field
--------------------------------------

You can declare a serializer in the :ref:`field metadata
<topics-items-fields>`. The serializer must be a callable which receives a
value and returns its serialized form.

Example::

      from scrapy.item import Item, Field

      def serialize_price(value):
         return '$ %s' % str(value)

      class Product(Item):
          name = Field()
          price = Field(serializer=serialize_price)


2. Overriding the serialize_field() method
------------------------------------------

You can also override the :meth:`~BaseItemExporter.serialize` method to
customize how your field value will be exported.

Make sure you call the base class :meth:`~BaseItemExporter.serialize` method
after your custom code. 

Example::

      from scrapy.contrib.exporter import XmlItemExporter

      class ProductXmlExporter(XmlItemExporter):

          def serialize_field(self, field, name, value):
              if filed == 'price':
                  return '$ %s' % str(value)
              return super(Product, self).serialize_field(field, name, value)
             
.. _topics-exporters-reference:

Built-in Item Exporters reference
=================================

For the examples shown in the following exporters we always assume we export
these two items::

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
   populate their respective attributes: :attr:`fields_to_export`,
   :attr:`export_empty_fields`, :attr:`encoding`.

   .. method:: export_item(item)

      Exports the item to the specific exporter format. This method must be
      implemented in subclasses.

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

      Makes the exporter initialize the export process, in here exporters may
      output information required by the exporter's format.

   .. method:: finish_exporting()

      You must call it when there are no more items to export, so the exporter
      can close the serialization output, for those formats that require it
      (like XML).

   .. attribute:: fields_to_export

      A list with the name of the fields that will be exported, or None if you
      want to export all fields. Defaults to None.

      Some exporters (like :class:`CsvItemExporter`) respect the order of the
      fields defined in this attribute.

   .. attribute:: export_empty_fields

      Whether to include empty/unpopulated item fields in the exported data.
      Defaults to ``False``.

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


CsvItemExporter
---------------

.. class:: CsvItemExporter(file, include_headers_line=False, \**kwargs)

   Exports Items in CSV format to the given file-like object. If the
   :attr:`fields_to_export` attribute is set, it will be used to define the
   CSV columns and their order. The :attr:`export_empty_fields` attribute has
   no effect on this exporter.

   :param include_headers_line: If enabled, makes the exporter output a header
       line with the field names taken from
       :attr:`BaseItemExporter.fields_to_export` so that attribute must also be
       set in order to work (otherwise it raises a :exc:`RuntimeError`)
   :type include_headers_line: boolean

   The additional keyword arguments of this constructor are passed to the
   :class:`BaseItemExporter` constructor, and then to the `csv.writer`_
   constructor, so you can use any `csv.writer` constructor argument to
   customize this exporter.

   A typical output of this exporter would be::

      Color TV,1200
      DVD player,200
      
.. _csv.writer: http://docs.python.org/library/csv.html#csv.writer

PickleItemExporter
------------------

.. class:: PickleItemExporter(file, protocol=0, \**kwargs)

   Exports Items in pickle format to the given file-like object. 
   
   :param protocol: The pickle protocol to use.
   :type protocol: int

   For more information, refer to the `pickle module documentation`_.

   The additional keyword arguments of this constructor are passed to the
   :class:`BaseItemExporter` constructor.

   This isn't a human readable format, so no output examples are provided.

.. _pickle module documentation: http://docs.python.org/library/pickle.html

PprintItemExporter
------------------

.. class:: PprintItemExporter(file, \**kwargs)

   Exports Items in pretty print format to the specified file object.

   The additional keyword arguments of this constructor are passed to the
   :class:`BaseItemExporter` constructor.

   A typical output of this exporter would be::

        {'name': 'Color TV', 'price': '1200'}
        {'name': 'DVD player', 'price': '200'}

   Longer lines (when present) are pretty-formatted.

JsonLinesItemExporter
---------------------

.. module:: scrapy.contrib.exporter.jsonlines
   :synopsis: JsonLines Item Exporter

.. class:: JsonLinesItemExporter(file, \**kwargs)

   Exports Items in JSON format to the specified file-like object, writing one
   JSON-encoded item per line. The additional constructor arguments are passed
   to the :class:`BaseItemExporter` constructor, and to the `JSONEncoder`_
   constructor, so you can use any `JSONEncoder`_ constructor argument to
   customize the exporter.

   The default output of this exporter would be::

        {"name": "Color TV", "price": "1200"}
        {"name": "DVD player", "price": "200"}

.. _JSONEncoder: http://docs.python.org/library/json.html#json.JSONEncoder

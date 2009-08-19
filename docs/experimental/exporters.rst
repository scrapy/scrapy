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
instantiated you exporter, you have to call the
:meth:`~BaseItemExporter.export` method with each item you want to export.

Here you can see a typical Item Exporter usage in an :ref:`Item Pipeline
<topics-item-pipeline>`::

   from scrapy.xlib.pydispatch import dispatcher
   from scrapy.contrib.exporter import XmlItemExporter

   class XmlExportPipeline(object):

       def __init__(self):
           dispatcher.connect(self.domain_open, signals.domain_open) 
           dispatcher.connect(self.domain_closed, signals.domain_closed)

       def domain_open(self, domain):
           self.file = open('%s_products.xml' % domain)
           self.exporter = XmlItemExporter(self.file)

       def domain_closed(self, domain):
           self.exporter.close()
           self.file.close()

       def process_item(self, domain, item):
           self.exporter.export(item)
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

1. Declaring a serializer in the field
--------------------------------------

You can declare a serializer in the :ref:`field metadata
<topics-newitems-fields>`. The serializer must be a callable which receives a
value and returns its serialized form.

Example::

      from scrapy.newitem import Item, Field

      def serialize_price(value):
         return '$ %s' % str(value)

      class Product(Item):
          name = Field()
          price = Field(serializer=serialize_price)


2. Overriding the serialize() method
------------------------------------

You can also override the :meth:`~BaseItemExporter.serialize` method to
customize how your field value will be exported.

Make sure you call the base class :meth:`~BaseItemExporter.serialize` method
after your custom code. 

Example::

      from scrapy.contrib.exporter import XmlItemExporter

      class ProductXmlExporter(XmlItemExporter):

          def serialize(self, field, name, value):
              if filed == 'price':
                  return '$ %s' % str(value)
              return super(Product, self).serialize(field, name, value)
             
.. _topics-exporters-reference:

Built-in Item Exporters reference
=================================

For the examples shown in the following exporters we always assume we export
these two items::

    Item(name='Color TV', price='1200')
    Item(name='DVD player', price='200')

BaseItemExporter
----------------

.. class:: BaseItemExporter

   This is the base class for all Item Exporters, and it's an abstract class.

   .. method:: export(item)

      Exports the item to the specific exporter format. This method must be
      implemented in subclasses.

   .. method:: serialize_default(field, name, value)

      Serializes the field value to ``str``. You can override this method in
      custom Item Exporters.

   .. method:: close()

      Called when there are no more items to export, so the exporter can close
      the serialization, for those formats that require it (like XML).

   .. attribute:: fields_to_export

      A list with the name of the fields that will be exported, or None if you
      want to export all fields. Defaults to None.

      Some exporters (like :class:`CsvItemExporter`) respect the order of the
      fields defined in this attribute.

   .. attribute:: export_empty_elements

      Whether to include empty elements in the exported XML (in case of
      empty/missing fields). Defaults to ``False``.

.. highlight:: none

XmlItemExporter
---------------

.. class:: XmlItemExporter(file)

   Exports Items in XML format to the specified file object. You must also set
   the :attr:`fields_to_export` attribute to use it.

   The default output of this exporter would be::

       <?xml version="1.0" encoding="iso-8859-1"?>
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

   .. attribute:: root_element

      The name of root element in the exported XML. Defaults to ``'items'``.

   .. attribute:: item_element

      The name of each item element in the exported XML. Defaults to ``'item'``.

CsvItemExporter
---------------

.. class:: CsvItemExporter(\*args, \**kwargs)

   Exports Items in CSV format. The constructor arguments will be passed to the
   `csv.writer`_ constructor. This exporter respects the order of fields in the
   :attr:`BaseItemExporter.fields_to_export` attribute.

   The default output of this exporter would be::

      Color TV,1200
      DVD player,200
      
   .. attribute:: include_headers_line

      If ``True`` the first line in the CSV export will include the name of the
      fields columns, taken from the :attr:`BaseItemExporter.fields_to_export`
      attribute. Defaults to ``False``.

.. _csv.writer: http://docs.python.org/library/csv.html#csv.writer

PickleItemExporter
------------------

.. class:: PickleItemExporter(\*args, \**kwargs)

   Exports Items in pickle format. The constructor arguments will be passed to
   the `Pickler`_ constructor. This is a binary format, so no output examples
   are provided.

.. _Pickler: http://docs.python.org/library/pickle.html#pickle.Pickler

PprintItemExporter
------------------

.. class:: PprintItemExporter(file)

   Exports Items in pretty print format to the specified file object.

   The default output of this exporter would be::

        {'name': 'Color TV', 'price': '1200'}
        {'name': 'DVD player', 'price': '200'}

   Longer lines would get pretty-formatted.

JsonLinesItemExporter
---------------------

.. module:: scrapy.contrib.exporter.jsonlines
   :synopsis: JsonLines Item Exporter

.. class:: JsonLinesItemExporter(file, \*args, \**kwargs)

   Exports Items in JSON format to the specified file object, writing one
   serialized item per line. The additional constructor arguments are passed to
   the `JSONEncoder` constructor.

   The default output of this exporter would be::

        {"name": "Color TV", "price": "1200"}
        {"name": "DVD player", "price": "200"}

.. _JSONEncoder: http://docs.python.org/library/json.html#json.JSONEncoder

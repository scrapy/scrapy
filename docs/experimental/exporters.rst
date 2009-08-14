.. _topics-exporters:

==============
Item Exporters
==============

.. module:: scrapy.contrib.exporter
   :synopsis: Item Exporters

Once you have scraped your Items, you probably will want to use the data in some
external application. For this purpose Scrapy provides simple Item Exporters
that allow you to export your scraped Items in different formats.


Using Item Exporters
====================

In order to use a Item Exporter, you  must instantiate it with its required args
(different exporters require different args in order to work, look at the
reference of the specific Item Exporter in :ref:`topics-exporters-reference` )
then call the :meth:`~BaseItemExporter.export` method with the item to export as
its argument.

Here you can see a typical Item Exporter usage in a :ref:`Item Pipeline
<topics-item-pipeline>`::

   from scrapy.xlib.pydispatch import dispatcher
   from scrapy.contrib.exporter.jsonexporter import JSONItemExporter


   class ProductJSONPipeline(object):
       def __init__(self):
           dispatcher.connect(self.domain_open, signals.domain_open) 
           dispatcher.connect(self.domain_closed, signals.domain_closed)

       def domain_open(self, domain):
           self.file = open('%s_products.json' % domain)
           self.exporter = JSONItemExporter(self.file)

       def domain_closed(self, domain):
           self.file.close()

       def process_item(self, domain, item):
           self.exporter.export(item)
           return item


.. _topics-exporters-field-serialization:

Field serialization
===================

By default each field is serialized to its string representation using the 
:meth:`~BaseItemExporter._default_serializer` method.

You can customize how a field will be serialized in two ways:

1. Providing a ``serialize_(field-name)`` method in your custom Item Exporter.
2. Implementing a ``serializer`` method in a custom Field of your Item.

.. note:: This is the order of precedence, so if you provide both, the custom
   serialize_(field-name) method in the Item Exporter will be used.

In any case, your method must accept the same parameters as the
:meth:`~BaseItemExporter._default_serializer` method and return the serialized
version of the field in a string format.  

Let's see some examples on using the methods described above:

1. Providing a ``serialize_price`` method::

      from scrapy.contrib.exporter.jsonexporter import JSONItemExporter

      class ProductJSONExporter(JSONItemExporter):
          def serialize_price(self, field, name, value):
              return '$ %s' % str(value)
             
2. Using a custom ``PriceField``::

      from scrapy.newitem import Item, Field

      class PriceField(Field):
         def serializer(self, field, name, value):
             return '$ %s' % str(value)

      class Product(Item):
          name = Field()
          price = PriceField()
          stock = Field(default=0)
          last_updated = Field()


.. _topics-exporters-reference:

Available Item Exporters
========================

BaseItemExporter
----------------

.. class:: BaseItemExporter

   This is the base class for all Item Exporters.

   .. method:: export(item)

      Exports the item to the specific exporter format. Descendant classes must
      override this method.

   .. method:: _default_serializer(field, name, value)

      Serializes the field, the base implementation returns it string
      representation. You can override this in custom Item Exporters.


PprintItemExporter
------------------

.. class:: PprintItemExporter(file)

   Exports Items in preety print format to the specified file object.


.. class:: PickleItemExporter(\*args, \**kwargs)

   Exports Items in pickle format. The arguments in the constructor will be used
   to construct a ``cPickle.Pickler`` object.


CsvItemExporter
---------------

.. class:: CsvItemExporter(\*args, \**kwargs)

   Exports Items in CSV format. The arguments in the constructor will be used to
   construct a ``csv.writer`` object. You must also set its
   :attr:`~CsvItemExporter.fields_to_export` attribute to use it.

   .. attribute:: fields_to_export

      Iterable containing the Item Field names to be exported.       


XmlItemExporter
---------------

.. class:: XmlItemExporter(\*args, \**kwargs)

   Exports Items in XML format to the specified file object. You must also set its
   :attr:`~XmlItemExporter.fields_to_export` attribute to use it.

   .. attribute:: root_element

      The name of the root element in the exported file. It defaults to
      ``items``.

   .. attribute:: item_element

      The name of each item element in the exported file. It defaults to
      ``item``.

   .. attribute:: include_empty_elements

      Whether to include or not empty elements in the exported file. It defaults to
      ``False``.

   .. attribute:: fields_to_export

      Iterable containing the Item Field names to be exported. 


JSONItemExporter
----------------

.. class:: scrapy.contrib.exporter.jsonexporter.JsonItemExporter(file)

   Exports Items in JSON format to the specified file object.


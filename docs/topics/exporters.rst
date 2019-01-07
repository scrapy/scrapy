.. currentmodule:: scrapy.exporters

.. _topics-exporters:

==============
Item Exporters
==============

Once you have scraped your items, you often want to persist or export those
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

Here you can see an :doc:`Item Pipeline <item-pipeline>` which uses multiple
Item Exporters to group scraped items to different files according to the
value of one of their fields::

    from scrapy.exporters import XmlItemExporter

    class PerYearXmlExportPipeline(object):
        """Distribute items across multiple XML files according to their 'year' field"""

        def open_spider(self, spider):
            self.year_to_exporter = {}

        def close_spider(self, spider):
            for exporter in self.year_to_exporter.values():
                exporter.finish_exporting()
                exporter.file.close()

        def _exporter_for_item(self, item):
            year = item['year']
            if year not in self.year_to_exporter:
                f = open('{}.xml'.format(year), 'wb')
                exporter = XmlItemExporter(f)
                exporter.start_exporting()
                self.year_to_exporter[year] = exporter
            return self.year_to_exporter[year]

        def process_item(self, item, spider):
            exporter = self._exporter_for_item(item)
            exporter.export_item(item)
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

If you use :class:`~scrapy.Item` you can declare a serializer in the
:ref:`field metadata <topics-items-fields>`. The serializer must be 
a callable which receives a value and returns its serialized form.

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

      from scrapy.exporter import XmlItemExporter

      class ProductXmlExporter(XmlItemExporter):

          def serialize_field(self, field, name, value):
              if field == 'price':
                  return '$ %s' % str(value)
              return super(Product, self).serialize_field(field, name, value)

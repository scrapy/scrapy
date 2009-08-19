from cPickle import Pickler
from cStringIO import StringIO

from twisted.trial import unittest

from scrapy.newitem import Item, Field

from scrapy.contrib.exporter import BaseItemExporter, PprintItemExporter, \
    PickleItemExporter, CsvItemExporter, XmlItemExporter

class TestItem(Item):
    name = Field()
    age = Field()


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.i = TestItem(name=u'John', age='22')
        self.ie = BaseItemExporter()

        self.output = StringIO()

class BaseItemExporterTest(BaseTest):
        
    def test_export(self):
        self.assertRaises(NotImplementedError, self.ie.export_item, self.i)

    def test_serialize(self):
        self.assertEqual(self.ie.serialize( \
            self.i.fields['name'], 'name', self.i['name']), 'John')
        self.assertEqual( \
            self.ie.serialize(self.i.fields['age'], 'age', self.i['age']), '22')

    def test_exporter_custom_serializer(self):
        class CustomItemExporter(BaseItemExporter):
            def serialize(self, field, name, value):
                if name == 'age':
                    return str(int(value) + 1)
                else:
                    return super(CustomItemExporter, self).serialize(field, \
                        name, value)

        ie = CustomItemExporter()

        self.assertEqual( \
            ie.serialize(self.i.fields['name'], 'name', self.i['name']), 'John')
        self.assertEqual(
            ie.serialize(self.i.fields['age'], 'age', self.i['age']), '23')

    def test_field_custom_serializer(self):
        def custom_serializer(value):
            return str(int(value) + 2)

        class CustomFieldItem(Item):
            name = Field()
            age = Field(serializer=custom_serializer)

        i = CustomFieldItem(name=u'John', age='22')

        self.assertEqual( \
            self.ie.serialize(i.fields['name'], 'name', i['name']), 'John')
        self.assertEqual( \
            self.ie.serialize(i.fields['age'], 'age', i['age']), '24')

    def test_fields_to_export(self):
        ie = BaseItemExporter()
        ie.fields_to_export = ['name']

        self.assertEqual(ie._get_fields_to_export(self.i), [('name', 'John')])


class PprintItemExporterTest(BaseTest):

    def test_export(self):
        ie = PprintItemExporter(self.output)
        ie.start_exporting()
        ie.export_item(self.i)
        ie.finish_exporting()

        self.assertEqual(self.output.getvalue(), "{'age': '22', 'name': u'John'}\n")


class PickleItemExporterTest(BaseTest):
        
    def test_export(self):
        output = StringIO()
        ie = PickleItemExporter(output)

        ie.start_exporting()
        ie.export_item(self.i)
        ie.finish_exporting()

        poutput = StringIO()
        p = Pickler(poutput)
        p.dump(dict(self.i))
        
        self.assertEqual(output.getvalue(), poutput.getvalue())


class CsvItemExporterTest(BaseTest):

    def test_export(self):
        ie = CsvItemExporter(self.output)
        ie.start_exporting()
        ie.export_item(self.i)
        ie.finish_exporting()

        self.assertEqual(self.output.getvalue(), '22,John\r\n')

    def test_header(self):
        ie = CsvItemExporter(self.output)
        ie.include_headers_line = True

        self.assertRaises(RuntimeError, ie.start_exporting)

        ie.fields_to_export = self.i.fields.keys()
        ie.start_exporting()
        ie.export_item(self.i)
        ie.finish_exporting()

        self.assertEqual(self.output.getvalue(), 'age,name\r\n22,John\r\n')


class XmlItemExporterTest(BaseTest):

    def test_export(self):
        ie = XmlItemExporter(self.output)
        ie.start_exporting()
        ie.export_item(self.i)
        ie.finish_exporting()

        expected_value = '<?xml version="1.0" encoding="iso-8859-1"?>\n<items><item><age>22</age><name>John</name></item></items>'

        self.assertEqual(self.output.getvalue(), expected_value)


class JSONItemExporterTest(BaseTest):

    def setUp(self):
        try:
            import json
        except ImportError:
            try:
                import simplejson
            except ImportError:
                raise unittest.SkipTest("simplejson module not available") 

        from scrapy.contrib.exporter.jsonlines import JsonLinesItemExporter

        super(JSONItemExporterTest, self).__init__()

    def test_export(self):

        ie = JsonLinesItemExporter(output)
        ie.start_exporting()
        ie.export_item(self.i)
        ie.finish_exporting()

        self.assertEqual(output.getvalue(), '{"age": "22", "name": "John"}\n')


if __name__ == '__main__':
    unittest.main()

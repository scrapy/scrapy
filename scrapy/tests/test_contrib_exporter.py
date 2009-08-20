import cPickle as pickle
from cStringIO import StringIO

from twisted.trial import unittest

from scrapy.item import Item, Field
from scrapy.contrib.exporter import BaseItemExporter, PprintItemExporter, \
    PickleItemExporter, CsvItemExporter, XmlItemExporter

class TestItem(Item):
    name = Field()
    age = Field()


class BaseItemExporterTest(unittest.TestCase):

    def setUp(self):
        self.i = TestItem(name=u'John', age='22')
        self.output = StringIO()
        self.ie = self._get_exporter()

    def _get_exporter(self):
        return BaseItemExporter()

    def _check_output(self):
        pass

    def test_export_item(self):
        self.ie.start_exporting()
        try:
            self.ie.export_item(self.i)
        except NotImplementedError:
            if self.ie.__class__ is not BaseItemExporter:
                raise
        self.ie.finish_exporting()
        self._check_output()

    def test_serialize_field(self):
        self.assertEqual(self.ie.serialize_field( \
            self.i.fields['name'], 'name', self.i['name']), 'John')
        self.assertEqual( \
            self.ie.serialize_field(self.i.fields['age'], 'age', self.i['age']), '22')

    def test_exporter_custom_serializer(self):
        class CustomItemExporter(BaseItemExporter):
            def serialize_field(self, field, name, value):
                if name == 'age':
                    return str(int(value) + 1)
                else:
                    return super(CustomItemExporter, self).serialize_field(field, \
                        name, value)

        ie = CustomItemExporter()

        self.assertEqual( \
            ie.serialize_field(self.i.fields['name'], 'name', self.i['name']), 'John')
        self.assertEqual(
            ie.serialize_field(self.i.fields['age'], 'age', self.i['age']), '23')

    def test_field_custom_serializer(self):
        def custom_serializer(value):
            return str(int(value) + 2)

        class CustomFieldItem(Item):
            name = Field()
            age = Field(serializer=custom_serializer)

        i = CustomFieldItem(name=u'John', age='22')

        self.assertEqual( \
            self.ie.serialize_field(i.fields['name'], 'name', i['name']), 'John')
        self.assertEqual( \
            self.ie.serialize_field(i.fields['age'], 'age', i['age']), '24')

    def test_fields_to_export(self):
        ie = BaseItemExporter()
        ie.fields_to_export = ['name']

        self.assertEqual(list(ie._get_serialized_fields(self.i)), [('name', 'John')])

class PprintItemExporterTest(BaseItemExporterTest):

    def _get_exporter(self):
        return PprintItemExporter(self.output)

    def _check_output(self):
        self.assertEqual(dict(self.i), eval(self.output.getvalue()))


class PickleItemExporterTest(BaseItemExporterTest):
        
    def _get_exporter(self):
        return PickleItemExporter(self.output)

    def _check_output(self):
        self.assertEqual(dict(self.i), pickle.loads(self.output.getvalue()))

class CsvItemExporterTest(BaseItemExporterTest):

    def _get_exporter(self):
        return CsvItemExporter(self.output)

    def _check_output(self):
        self.assertEqual(self.output.getvalue(), '22,John\r\n')

    def test_header(self):
        output = StringIO()
        ie = CsvItemExporter(output)
        ie.include_headers_line = True

        self.assertRaises(RuntimeError, ie.start_exporting)

        ie.fields_to_export = self.i.fields.keys()
        ie.start_exporting()
        ie.export_item(self.i)
        ie.finish_exporting()

        self.assertEqual(output.getvalue(), 'age,name\r\n22,John\r\n')


class XmlItemExporterTest(BaseItemExporterTest):

    def _get_exporter(self):
        return XmlItemExporter(self.output)

    def _check_output(self):
        expected_value = '<?xml version="1.0" encoding="iso-8859-1"?>\n<items><item><age>22</age><name>John</name></item></items>'
        self.assertEqual(self.output.getvalue(), expected_value)


class JsonLinesItemExporterTest(BaseItemExporterTest):

    def _get_exporter(self):
        try:
            import json
        except ImportError:
            try:
                import simplejson
            except ImportError:
                raise unittest.SkipTest("simplejson module not available") 
        from scrapy.contrib.exporter.jsonlines import JsonLinesItemExporter
        return JsonLinesItemExporter(self.output)

    def _check_output(self):
        self.assertEqual(self.output.getvalue(), '{"age": "22", "name": "John"}\n')


if __name__ == '__main__':
    unittest.main()

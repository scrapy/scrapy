from cPickle import Pickler
from cStringIO import StringIO
import pprint
from twisted.trial import unittest

from scrapy.newitem import Item, Field
from scrapy.newitem.exporters import *

class TestItem(Item):
    name = Field()
    age = Field()


class BaseItemExporterTest(unittest.TestCase):
    
    def test_export(self):
        i = TestItem(name=u'John', age=22)

        ie = BaseItemExporter()

        self.assertRaises(NotImplementedError, ie.export, i)

    def test_default_serializer(self):
        i = TestItem(name=u'John', age=22)

        ie = BaseItemExporter()

        self.assertEqual(ie._serialize_field(i.fields['name'], 'name', i['name']), 'John')
        self.assertEqual( ie._serialize_field(i.fields['age'], 'age', i['age']), '22')

    def test_exporter_custom_serializer(self):
        class CustomItemExporter(BaseItemExporter):
            def serialize_age(self, field, name, value):
                return str(value + 1)

        i = TestItem(name=u'John', age=22)

        ie = CustomItemExporter()

        self.assertEqual(ie._serialize_field(i.fields['name'], 'name', i['name']), 'John')
        self.assertEqual(ie._serialize_field(i.fields['age'], 'age', i['age']), '23')

    def test_field_custom_serializer(self):
        class CustomField(Field):
            def serializer(self, field, name, value):
                return str(value + 2)

        class CustomFieldItem(Item):
            name = Field()
            age = CustomField()

        i = CustomFieldItem(name=u'John', age=22)

        ie = BaseItemExporter()

        self.assertEqual(ie._serialize_field(i.fields['name'], 'name', i['name']), 'John')
        self.assertEqual(ie._serialize_field(i.fields['age'], 'age', i['age']), '24')


class PprintItemExporterTest(unittest.TestCase):

    def test_export(self):
        i = TestItem(name=u'John', age=22)

        output = StringIO()
        ie = PprintItemExporter(output)
        ie.export(i)

        self.assertEqual(output.getvalue(), "{'age': 22, 'name': u'John'}\n")


class PickleItemExporterTest(unittest.TestCase):
        
    def test_export(self):
        i = TestItem(name=u'John', age=22)

        output = StringIO()
        ie = PickleItemExporter(output)
        ie.export(i)

        poutput = StringIO()
        p = Pickler(poutput)
        p.dump(dict(i))
        
        self.assertEqual(output.getvalue(), poutput.getvalue())


class CsvItemExporterTest(unittest.TestCase):

    def test_export(self):
        i = TestItem(name=u'John', age=22)

        output = StringIO()
        ie = CsvItemExporter(output)
        ie.fields_to_export = i.fields.keys()
        ie.export(i)

        self.assertEqual(output.getvalue(), 'age,name\r\n22,John\r\n')


class XmlItemExporterTest(unittest.TestCase):

    def test_export(self):
        i = TestItem(name=u'John', age=22)

        output = StringIO()
        ie = XmlItemExporter(output)
        ie.fields_to_export = i.fields.keys()
        ie.export(i)

        self.assertEqual(output.getvalue(), '<?xml version="1.0" encoding="iso-8859-1"?>\n<items><item><age>22</age><name>John</name></item>')


class JSONItemExporterTest(unittest.TestCase):

    def setUp(self):
        try:
            from scrapy.newitem.exporters.jsonexporter import JSONItemExporter
            self.output = StringIO()
            self.ie = JSONItemExporter(self.output)

        except ImportError, e:
            raise unittest.SkipTest("Json library not available") 

    def test_export(self):
        i = TestItem(name=u'John', age=22)

        self.ie.export(i)

        self.assertEqual(self.output.getvalue(), '{"age": 22, "name": "John"}\n')


import unittest, json, cPickle as pickle
from cStringIO import StringIO
import lxml.etree
import re

from scrapy.item import Item, Field
from scrapy.utils.python import str_to_unicode
from scrapy.contrib.exporter import BaseItemExporter, PprintItemExporter, \
    PickleItemExporter, CsvItemExporter, XmlItemExporter, JsonLinesItemExporter, \
    JsonItemExporter, PythonItemExporter

class TestItem(Item):
    name = Field()
    age = Field()


class BaseItemExporterTest(unittest.TestCase):

    def setUp(self):
        self.i = TestItem(name=u'John\xa3', age='22')
        self.output = StringIO()
        self.ie = self._get_exporter()

    def _get_exporter(self, **kwargs):
        return BaseItemExporter(**kwargs)

    def _check_output(self):
        pass

    def _assert_expected_item(self, exported_dict):
        for k, v in exported_dict.items():
            exported_dict[k] = str_to_unicode(v)
        self.assertEqual(self.i, exported_dict)

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
            self.i.fields['name'], 'name', self.i['name']), 'John\xc2\xa3')
        self.assertEqual( \
            self.ie.serialize_field(self.i.fields['age'], 'age', self.i['age']), '22')

    def test_fields_to_export(self):
        ie = self._get_exporter(fields_to_export=['name'])
        self.assertEqual(list(ie._get_serialized_fields(self.i)), [('name', 'John\xc2\xa3')])

        ie = self._get_exporter(fields_to_export=['name'], encoding='latin-1')
        name = list(ie._get_serialized_fields(self.i))[0][1]
        assert isinstance(name, str)
        self.assertEqual(name, 'John\xa3')

    def test_field_custom_serializer(self):
        def custom_serializer(value):
            return str(int(value) + 2)

        class CustomFieldItem(Item):
            name = Field()
            age = Field(serializer=custom_serializer)

        i = CustomFieldItem(name=u'John\xa3', age='22')

        ie = self._get_exporter()
        self.assertEqual(ie.serialize_field(i.fields['name'], 'name', i['name']), 'John\xc2\xa3')
        self.assertEqual(ie.serialize_field(i.fields['age'], 'age', i['age']), '24')

class PythonItemExporterTest(BaseItemExporterTest):
    def _get_exporter(self, **kwargs):
        return PythonItemExporter(**kwargs)

    def test_nested_item(self):
        i1 = TestItem(name=u'Joseph', age='22')
        i2 = TestItem(name=u'Maria', age=i1)
        i3 = TestItem(name=u'Jesus', age=i2)
        ie = self._get_exporter()
        exported = ie.export_item(i3)
        self.assertEqual(type(exported), dict)
        self.assertEqual(exported, {'age': {'age': {'age': '22', 'name': u'Joseph'}, 'name': u'Maria'}, 'name': 'Jesus'})
        self.assertEqual(type(exported['age']), dict)
        self.assertEqual(type(exported['age']['age']), dict)

    def test_export_list(self):
        i1 = TestItem(name=u'Joseph', age='22')
        i2 = TestItem(name=u'Maria', age=[i1])
        i3 = TestItem(name=u'Jesus', age=[i2])
        ie = self._get_exporter()
        exported = ie.export_item(i3)
        self.assertEqual(exported, {'age': [{'age': [{'age': '22', 'name': u'Joseph'}], 'name': u'Maria'}], 'name': 'Jesus'})
        self.assertEqual(type(exported['age'][0]), dict)
        self.assertEqual(type(exported['age'][0]['age'][0]), dict)

    def test_export_item_dict_list(self):
        i1 = TestItem(name=u'Joseph', age='22')
        i2 = dict(name=u'Maria', age=[i1])
        i3 = TestItem(name=u'Jesus', age=[i2])
        ie = self._get_exporter()
        exported = ie.export_item(i3)
        self.assertEqual(exported, {'age': [{'age': [{'age': '22', 'name': u'Joseph'}], 'name': u'Maria'}], 'name': 'Jesus'})
        self.assertEqual(type(exported['age'][0]), dict)
        self.assertEqual(type(exported['age'][0]['age'][0]), dict)

class PprintItemExporterTest(BaseItemExporterTest):

    def _get_exporter(self, **kwargs):
        return PprintItemExporter(self.output, **kwargs)

    def _check_output(self):
        self._assert_expected_item(eval(self.output.getvalue()))

class PickleItemExporterTest(BaseItemExporterTest):

    def _get_exporter(self, **kwargs):
        return PickleItemExporter(self.output, **kwargs)

    def _check_output(self):
        self._assert_expected_item(pickle.loads(self.output.getvalue()))

    def test_export_multiple_items(self):
        i1 = TestItem(name='hello', age='world')
        i2 = TestItem(name='bye', age='world')
        f = StringIO()
        ie = PickleItemExporter(f)
        ie.start_exporting()
        ie.export_item(i1)
        ie.export_item(i2)
        ie.finish_exporting()
        f.reset()
        self.assertEqual(pickle.load(f), i1)
        self.assertEqual(pickle.load(f), i2)


class CsvItemExporterTest(BaseItemExporterTest):

    def _get_exporter(self, **kwargs):
        return CsvItemExporter(self.output, **kwargs)

    def assertCsvEqual(self, first, second, msg=None):
        csvsplit = lambda csv: [sorted(re.split(r'(,|\s+)', line))
                                for line in csv.splitlines(True)]
        return self.assertEqual(csvsplit(first), csvsplit(second), msg)

    def _check_output(self):
        self.assertCsvEqual(self.output.getvalue(), 'age,name\r\n22,John\xc2\xa3\r\n')

    def test_header(self):
        output = StringIO()
        ie = CsvItemExporter(output, fields_to_export=self.i.fields.keys())
        ie.start_exporting()
        ie.export_item(self.i)
        ie.finish_exporting()
        self.assertCsvEqual(output.getvalue(), 'age,name\r\n22,John\xc2\xa3\r\n')

        output = StringIO()
        ie = CsvItemExporter(output, fields_to_export=['age'])
        ie.start_exporting()
        ie.export_item(self.i)
        ie.finish_exporting()
        self.assertCsvEqual(output.getvalue(), 'age\r\n22\r\n')

        output = StringIO()
        ie = CsvItemExporter(output)
        ie.start_exporting()
        ie.export_item(self.i)
        ie.export_item(self.i)
        ie.finish_exporting()
        self.assertCsvEqual(output.getvalue(), 'age,name\r\n22,John\xc2\xa3\r\n22,John\xc2\xa3\r\n')

        output = StringIO()
        ie = CsvItemExporter(output, include_headers_line=False)
        ie.start_exporting()
        ie.export_item(self.i)
        ie.finish_exporting()
        self.assertCsvEqual(output.getvalue(), '22,John\xc2\xa3\r\n')

    def test_join_multivalue(self):
        class TestItem2(Item):
            name = Field()
            friends = Field()

        i = TestItem2(name='John', friends=['Mary', 'Paul'])
        output = StringIO()
        ie = CsvItemExporter(output, include_headers_line=False)
        ie.start_exporting()
        ie.export_item(i)
        ie.finish_exporting()
        self.assertCsvEqual(output.getvalue(), '"Mary,Paul",John\r\n')

class XmlItemExporterTest(BaseItemExporterTest):

    def _get_exporter(self, **kwargs):
        return XmlItemExporter(self.output, **kwargs)

    def assertXmlEquivalent(self, first, second, msg=None):
        def xmltuple(elem):
            children = list(elem.iterchildren())
            if children:
                return [(child.tag, sorted(xmltuple(child)))
                        for child in children]
            else:
                return [(elem.tag, [(elem.text, ())])]
        def xmlsplit(xmlcontent):
            doc = lxml.etree.fromstring(xmlcontent)
            return xmltuple(doc)
        return self.assertEqual(xmlsplit(first), xmlsplit(second), msg)

    def _check_output(self):
        expected_value = '<?xml version="1.0" encoding="utf-8"?>\n<items><item><age>22</age><name>John\xc2\xa3</name></item></items>'
        self.assertXmlEquivalent(self.output.getvalue(), expected_value)

    def test_multivalued_fields(self):
        output = StringIO()
        item = TestItem(name=[u'John\xa3', u'Doe'])
        ie = XmlItemExporter(output)
        ie.start_exporting()
        ie.export_item(item)
        ie.finish_exporting()
        expected_value = '<?xml version="1.0" encoding="utf-8"?>\n<items><item><name><value>John\xc2\xa3</value><value>Doe</value></name></item></items>'
        self.assertXmlEquivalent(output.getvalue(), expected_value)

    def test_nested_item(self):
        output = StringIO()
        i1 = TestItem(name=u'foo\xa3hoo', age='22')
        i2 = TestItem(name=u'bar', age=i1)
        i3 = TestItem(name=u'buz', age=i2)
        ie = XmlItemExporter(output)
        ie.start_exporting()
        ie.export_item(i3)
        ie.finish_exporting()
        expected_value = '<?xml version="1.0" encoding="utf-8"?>\n'\
                '<items><item>'\
                    '<age>'\
                        '<age>'\
                            '<age>22</age>'\
                            '<name>foo\xc2\xa3hoo</name>'\
                        '</age>'\
                        '<name>bar</name>'\
                    '</age>'\
                    '<name>buz</name>'\
                '</item></items>'
        self.assertXmlEquivalent(output.getvalue(), expected_value)

    def test_nested_list_item(self):
        output = StringIO()
        i1 = TestItem(name=u'foo')
        i2 = TestItem(name=u'bar')
        i3 = TestItem(name=u'buz', age=[i1, i2])
        ie = XmlItemExporter(output)
        ie.start_exporting()
        ie.export_item(i3)
        ie.finish_exporting()
        expected_value =  '<?xml version="1.0" encoding="utf-8"?>\n'\
                '<items><item>'\
                    '<age>'\
                        '<value><name>foo</name></value>'\
                        '<value><name>bar</name></value>'\
                    '</age>'\
                    '<name>buz</name>'\
                '</item></items>'
        self.assertXmlEquivalent(output.getvalue(), expected_value)


class JsonLinesItemExporterTest(BaseItemExporterTest):

    _expected_nested = {'name': u'Jesus', 'age': {'name': 'Maria', 'age': {'name': 'Joseph', 'age': '22'}}}

    def _get_exporter(self, **kwargs):
        return JsonLinesItemExporter(self.output, **kwargs)

    def _check_output(self):
        exported = json.loads(self.output.getvalue().strip())
        self.assertEqual(exported, dict(self.i))

    def test_nested_item(self):
        i1 = TestItem(name=u'Joseph', age='22')
        i2 = TestItem(name=u'Maria', age=i1)
        i3 = TestItem(name=u'Jesus', age=i2)
        self.ie.start_exporting()
        self.ie.export_item(i3)
        self.ie.finish_exporting()
        exported = json.loads(self.output.getvalue())
        self.assertEqual(exported, self._expected_nested)

    def test_extra_keywords(self):
        self.ie = self._get_exporter(sort_keys=True)
        self.test_export_item()
        self._check_output()
        self.assertRaises(TypeError, self._get_exporter, foo_unknown_keyword_bar=True)


class JsonItemExporterTest(JsonLinesItemExporterTest):

    _expected_nested = [JsonLinesItemExporterTest._expected_nested]

    def _get_exporter(self, **kwargs):
        return JsonItemExporter(self.output, **kwargs)

    def _check_output(self):
        exported = json.loads(self.output.getvalue().strip())
        self.assertEqual(exported, [dict(self.i)])

    def test_two_items(self):
        self.ie.start_exporting()
        self.ie.export_item(self.i)
        self.ie.export_item(self.i)
        self.ie.finish_exporting()
        exported = json.loads(self.output.getvalue())
        self.assertEqual(exported, [dict(self.i), dict(self.i)])

    def test_nested_item(self):
        i1 = TestItem(name=u'Joseph\xa3', age='22')
        i2 = TestItem(name=u'Maria', age=i1)
        i3 = TestItem(name=u'Jesus', age=i2)
        self.ie.start_exporting()
        self.ie.export_item(i3)
        self.ie.finish_exporting()
        exported = json.loads(self.output.getvalue())
        expected = {'name': u'Jesus', 'age': {'name': 'Maria', 'age': dict(i1)}}
        self.assertEqual(exported, [expected])

class CustomItemExporterTest(unittest.TestCase):

    def test_exporter_custom_serializer(self):
        class CustomItemExporter(BaseItemExporter):
            def serialize_field(self, field, name, value):
                if name == 'age':
                    return str(int(value) + 1)
                else:
                    return super(CustomItemExporter, self).serialize_field(field, \
                        name, value)

        i = TestItem(name=u'John', age='22')
        ie = CustomItemExporter()

        self.assertEqual( \
            ie.serialize_field(i.fields['name'], 'name', i['name']), 'John')
        self.assertEqual(
            ie.serialize_field(i.fields['age'], 'age', i['age']), '23')


if __name__ == '__main__':
    unittest.main()

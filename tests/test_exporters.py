from __future__ import absolute_import
import re
import json
import unittest
from io import BytesIO
from six.moves import cPickle as pickle

import lxml.etree

from scrapy.item import Item, Field
from scrapy.utils.python import to_unicode
from scrapy.exporters import (
    BaseItemExporter, PprintItemExporter, PickleItemExporter, CsvItemExporter,
    XmlItemExporter, JsonLinesItemExporter, JsonItemExporter, PythonItemExporter
)


class TestItem(Item):
    name = Field()
    age = Field()


class BaseItemExporterTest(unittest.TestCase):

    def setUp(self):
        self.i = TestItem(name=u'John\xa3', age=u'22')
        self.output = BytesIO()
        self.ie = self._get_exporter()

    def _get_exporter(self, **kwargs):
        return BaseItemExporter(**kwargs)

    def _check_output(self):
        pass

    def _assert_expected_item(self, exported_dict):
        for k, v in exported_dict.items():
            exported_dict[k] = to_unicode(v)
        self.assertEqual(self.i, exported_dict)

    def assertItemExportWorks(self, item):
        self.ie.start_exporting()
        try:
            self.ie.export_item(item)
        except NotImplementedError:
            if self.ie.__class__ is not BaseItemExporter:
                raise
        self.ie.finish_exporting()
        self._check_output()

    def test_export_item(self):
        self.assertItemExportWorks(self.i)

    def test_export_dict_item(self):
        self.assertItemExportWorks(dict(self.i))

    def test_serialize_field(self):
        res = self.ie.serialize_field(self.i.fields['name'], 'name', self.i['name'])
        self.assertEqual(res, u'John\xa3')

        res = self.ie.serialize_field(self.i.fields['age'], 'age', self.i['age'])
        self.assertEqual(res, u'22')

    def test_fields_to_export(self):
        ie = self._get_exporter(fields_to_export=['name'])
        self.assertEqual(list(ie._get_serialized_fields(self.i)), [('name', u'John\xa3')])

    def test_field_custom_serializer(self):
        def custom_serializer(value):
            return str(int(value) + 2)

        class CustomFieldItem(Item):
            name = Field()
            age = Field(serializer=custom_serializer)

        i = CustomFieldItem(name=u'John\xa3', age=u'22')

        ie = self._get_exporter()
        self.assertEqual(ie.serialize_field(i.fields['name'], 'name', i['name']), u'John\xa3')
        self.assertEqual(ie.serialize_field(i.fields['age'], 'age', i['age']), '24')


class MidRefactoringBaseItemExporterTest(BaseItemExporterTest):
    """Class introduced just to keep old behavior of BaseItemExporterTest for the
    test cases that inherit from it while we make changes to exporters one by
    one -- a needed refactoring trick because the test cases are quite coupled.

    When we're done with the changes, we'll have ditched this class.
    """
    def test_serialize_field(self):
        if self.ie.__class__ is BaseItemExporter:
            return

        res = self.ie.serialize_field(self.i.fields['name'], 'name', self.i['name'])
        self.assertEqual(res, 'John\xc2\xa3')

        res = self.ie.serialize_field(self.i.fields['age'], 'age', self.i['age'])
        self.assertEqual(res, '22')

    def test_fields_to_export(self):
        if self.ie.__class__ is BaseItemExporter:
            return

        ie = self._get_exporter(fields_to_export=['name'])
        self.assertEqual(list(ie._get_serialized_fields(self.i)), [('name', 'John\xc2\xa3')])

        ie = self._get_exporter(fields_to_export=['name'], encoding='latin-1')
        name = list(ie._get_serialized_fields(self.i))[0][1]
        assert isinstance(name, str)
        self.assertEqual(name, 'John\xa3')

    def test_field_custom_serializer(self):
        if self.ie.__class__ is BaseItemExporter:
            return

        def custom_serializer(value):
            return str(int(value) + 2)

        class CustomFieldItem(Item):
            name = Field()
            age = Field(serializer=custom_serializer)

        i = CustomFieldItem(name=u'John\xa3', age='22')

        ie = self._get_exporter()
        self.assertEqual(ie.serialize_field(i.fields['name'], 'name', i['name']), 'John\xc2\xa3')
        self.assertEqual(ie.serialize_field(i.fields['age'], 'age', i['age']), '24')


class PythonItemExporterTest(MidRefactoringBaseItemExporterTest):
    def _get_exporter(self, **kwargs):
        return PythonItemExporter(**kwargs)

    def test_nested_item(self):
        i1 = TestItem(name=u'Joseph', age='22')
        i2 = dict(name=u'Maria', age=i1)
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
        f = BytesIO()
        ie = PickleItemExporter(f)
        ie.start_exporting()
        ie.export_item(i1)
        ie.export_item(i2)
        ie.finish_exporting()
        f.seek(0)
        self.assertEqual(pickle.load(f), i1)
        self.assertEqual(pickle.load(f), i2)


class CsvItemExporterTest(MidRefactoringBaseItemExporterTest):

    def _get_exporter(self, **kwargs):
        return CsvItemExporter(self.output, **kwargs)

    def assertCsvEqual(self, first, second, msg=None):
        csvsplit = lambda csv: [sorted(re.split(r'(,|\s+)', line))
                                for line in csv.splitlines(True)]
        return self.assertEqual(csvsplit(first), csvsplit(second), msg)

    def _check_output(self):
        self.assertCsvEqual(self.output.getvalue(), 'age,name\r\n22,John\xc2\xa3\r\n')

    def assertExportResult(self, item, expected, **kwargs):
        fp = BytesIO()
        ie = CsvItemExporter(fp, **kwargs)
        ie.start_exporting()
        ie.export_item(item)
        ie.finish_exporting()
        self.assertCsvEqual(fp.getvalue(), expected)

    def test_header_export_all(self):
        self.assertExportResult(
            item=self.i,
            fields_to_export=self.i.fields.keys(),
            expected='age,name\r\n22,John\xc2\xa3\r\n',
        )

    def test_header_export_all_dict(self):
        self.assertExportResult(
            item=dict(self.i),
            expected='age,name\r\n22,John\xc2\xa3\r\n',
        )

    def test_header_export_single_field(self):
        for item in [self.i, dict(self.i)]:
            self.assertExportResult(
                item=item,
                fields_to_export=['age'],
                expected='age\r\n22\r\n',
            )

    def test_header_export_two_items(self):
        for item in [self.i, dict(self.i)]:
            output = BytesIO()
            ie = CsvItemExporter(output)
            ie.start_exporting()
            ie.export_item(item)
            ie.export_item(item)
            ie.finish_exporting()
            self.assertCsvEqual(output.getvalue(), 'age,name\r\n22,John\xc2\xa3\r\n22,John\xc2\xa3\r\n')

    def test_header_no_header_line(self):
        for item in [self.i, dict(self.i)]:
            self.assertExportResult(
                item=item,
                include_headers_line=False,
                expected='22,John\xc2\xa3\r\n',
            )

    def test_join_multivalue(self):
        class TestItem2(Item):
            name = Field()
            friends = Field()

        for cls in TestItem2, dict:
            self.assertExportResult(
                item=cls(name='John', friends=['Mary', 'Paul']),
                include_headers_line=False,
                expected='"Mary,Paul",John\r\n',
            )


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

    def assertExportResult(self, item, expected_value):
        fp = BytesIO()
        ie = XmlItemExporter(fp)
        ie.start_exporting()
        ie.export_item(item)
        ie.finish_exporting()
        self.assertXmlEquivalent(fp.getvalue(), expected_value)

    def _check_output(self):
        expected_value = '<?xml version="1.0" encoding="utf-8"?>\n<items><item><age>22</age><name>John\xc2\xa3</name></item></items>'
        self.assertXmlEquivalent(self.output.getvalue(), expected_value)

    def test_multivalued_fields(self):
        self.assertExportResult(
            TestItem(name=[u'John\xa3', u'Doe']),
            '<?xml version="1.0" encoding="utf-8"?>\n<items><item><name><value>John\xc2\xa3</value><value>Doe</value></name></item></items>'
        )

    def test_nested_item(self):
        i1 = TestItem(name=u'foo\xa3hoo', age='22')
        i2 = dict(name=u'bar', age=i1)
        i3 = TestItem(name=u'buz', age=i2)

        self.assertExportResult(i3,
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<items>'
                '<item>'
                    '<age>'
                        '<age>'
                            '<age>22</age>'
                            '<name>foo\xc2\xa3hoo</name>'
                        '</age>'
                        '<name>bar</name>'
                    '</age>'
                    '<name>buz</name>'
                '</item>'
            '</items>'
        )

    def test_nested_list_item(self):
        i1 = TestItem(name=u'foo')
        i2 = dict(name=u'bar', v2={"egg": ["spam"]})
        i3 = TestItem(name=u'buz', age=[i1, i2])

        self.assertExportResult(i3,
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<items>'
                '<item>'
                    '<age>'
                        '<value><name>foo</name></value>'
                        '<value><name>bar</name><v2><egg><value>spam</value></egg></v2></value>'
                    '</age>'
                    '<name>buz</name>'
                '</item>'
            '</items>'
        )


class JsonLinesItemExporterTest(BaseItemExporterTest):

    _expected_nested = {'name': u'Jesus', 'age': {'name': 'Maria', 'age': {'name': 'Joseph', 'age': '22'}}}

    def _get_exporter(self, **kwargs):
        return JsonLinesItemExporter(self.output, **kwargs)

    def _check_output(self):
        exported = json.loads(self.output.getvalue().strip())
        self.assertEqual(exported, dict(self.i))

    def test_nested_item(self):
        i1 = TestItem(name=u'Joseph', age='22')
        i2 = dict(name=u'Maria', age=i1)
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

    def assertTwoItemsExported(self, item):
        self.ie.start_exporting()
        self.ie.export_item(item)
        self.ie.export_item(item)
        self.ie.finish_exporting()
        exported = json.loads(self.output.getvalue())
        self.assertEqual(exported, [dict(item), dict(item)])

    def test_two_items(self):
        self.assertTwoItemsExported(self.i)

    def test_two_dict_items(self):
        self.assertTwoItemsExported(dict(self.i))

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

    def test_nested_dict_item(self):
        i1 = dict(name=u'Joseph\xa3', age='22')
        i2 = TestItem(name=u'Maria', age=i1)
        i3 = dict(name=u'Jesus', age=i2)
        self.ie.start_exporting()
        self.ie.export_item(i3)
        self.ie.finish_exporting()
        exported = json.loads(self.output.getvalue())
        expected = {'name': u'Jesus', 'age': {'name': 'Maria', 'age': i1}}
        self.assertEqual(exported, [expected])


class CustomItemExporterTest(unittest.TestCase):

    def test_exporter_custom_serializer(self):
        class CustomItemExporter(BaseItemExporter):
            def serialize_field(self, field, name, value):
                if name == 'age':
                    return str(int(value) + 1)
                else:
                    return super(CustomItemExporter, self).serialize_field(field, name, value)

        i = TestItem(name=u'John', age='22')
        ie = CustomItemExporter()

        self.assertEqual(ie.serialize_field(i.fields['name'], 'name', i['name']), 'John')
        self.assertEqual(ie.serialize_field(i.fields['age'], 'age', i['age']), '23')

        i2 = {'name': u'John', 'age': '22'}
        self.assertEqual(ie.serialize_field({}, 'name', i2['name']), 'John')
        self.assertEqual(ie.serialize_field({}, 'age', i2['age']), '23')


if __name__ == '__main__':
    unittest.main()

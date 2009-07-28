"""
Item Exporters are used to export/serialize items into different formats.
"""

import csv
import pprint
from cPickle import Pickler
from xml.sax.saxutils import XMLGenerator

from scrapy.newitem import fields

__all__ = ['BaseItemExporter', 'PprintItemExporter', 'PickleItemExporter', \
    'CsvItemExporter', 'XmlItemExporter']

class BaseItemExporter(object):

    def __init__(self):
        self.field_serializers = {
            fields.TextField: self._serialize_text_field,
            fields.IntegerField: self._serialize_integer_field,
            fields.DecimalField: self._serialize_decimal_field,
            fields.FloatField: self._serialize_float_field,
            fields.BooleanField: self._serialize_boolean_field,
            fields.DateTimeField: self._serialize_datetime_field,
            fields.DateField: self._serialize_date_field,
            fields.TimeField: self._serialize_time_field,
            fields.ListField: self._serialize_list_field,
         }

    def export(self, item):
        raise NotImplementedError

    def close(self):
        pass

    def _serialize_field(self, field, name, value):
        try:
            fieldexp = self.field_serializers[field.__class__]
            return fieldexp(field, name, value)
        except KeyError:
            raise TypeError("%s doesn't know how to export field type: %s" % \
                self.__class__.__name__, field.__class__.__name__)

    def _serialize_text_field(self, field, name, value):
        return value.encode('utf-8')

    def _serialize_integer_field(self, field, name, value):
        return str(value)

    def _serialize_decimal_field(self, field, name, value):
        return str(value)

    def _serialize_float_field(self, field, name, value):
        return str(value)

    def _serialize_boolean_field(self, field, name, value):
        return '1' if value else '0'

    def _serialize_datetime_field(self, field, name, value):
        return str(value)

    def _serialize_date_field(self, field, name, value):
        return str(value)

    def _serialize_time_field(self, field, name, value):
        return str(value)

    def _serialize_list_field(self, field, name, value):
        item_field = field._field # TODO: should this attribute be public?
        return " ".join([self._serialize_field(item_field, name, v) for v in value])


class PprintItemExporter(BaseItemExporter):

    def __init__(self, file):
        super(PprintItemExporter, self).__init__(self)
        self.file = file

    def export(self, item):
        self.file.write(pprint.pprint(dict(item)) + '\n')


class PickleItemExporter(BaseItemExporter):

    def __init__(self, *args, **kwargs):
        super(PickleItemExporter, self).__init__(self)
        self.pickler = Pickler(*args, **kwargs)

    def export(self, item):
        self.pickler.dump(dict(item))


class CsvItemExporter(BaseItemExporter):

    fields_to_export = ()

    def __init__(self, *args, **kwargs):
        super(CsvItemExporter, self).__init__(self)
        self.csv_writer = csv.writer(*args, **kwargs)

    def export(self, item):
        self.csv_writer.writerow(self.fields_to_export)
        values = []
        for field in self.fields_to_export:
            if field in item:
                values.append(self._serialize_field(item.fields[field]), field, \
                    item[field])
            else:
                values.append('')
        self.csv_writer.writerow(values)


class XmlItemExporter(BaseItemExporter):

    item_element = 'item'
    root_element = 'items'
    include_empty_elements = False

    fields_to_export = ()

    def __init__(self, file):
        super(XmlItemExporter, self).__init__()
        self.xg = XMLGenerator(file)
        self.xg.startDocument()
        self.xg.startElement(self.root_element, {})

    def export(self, item):
        self.xg.startElement(self.item_element, {})
        for field in self.fields_to_export:
            if field in item:
                self.xg.startElement(self.item_element, {})
                self._export_xml_field(item.fields[field], field, item[field])
                self.xg.endElement(self.item_element)
            elif self.include_empty_elements:
                self.xg.startElement(self.item_element, {})
                self.xg.endElement()
        self.xg.endElement(self.item_element)

    def close(self):
        self.xg.endElement(self.root_element)
        self.xg.endDocument()

    def _export_xml_field(self, field, name, value):
        if isinstance(field, fields.ListField):
            for v in value:
                self._export_xml_field(field, 'value', v)
        self.xg.startElement(name, {})
        self.xg.characters(self._serialize_field(field, name, value))
        self.xg.endElement(name)

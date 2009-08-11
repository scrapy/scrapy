"""
Item Exporters are used to export/serialize items into different formats.
"""

import csv
import pprint
from cPickle import Pickler
from xml.sax.saxutils import XMLGenerator


__all__ = ['BaseItemExporter', 'PprintItemExporter', 'PickleItemExporter', \
    'CsvItemExporter', 'XmlItemExporter']


class BaseItemExporter(object):

    def export(self, item):
        raise NotImplementedError

    def close(self):
        pass

    def _serialize_field(self, field, name, value):
        if hasattr(self, 'serialize_%s' % name):
            serializer = getattr('serialize_%s' % name)
        elif hasattr(field, 'serializer'):
            serializer = field.serializer
        else:
            serializer = _default_serializer(field, name, value)

        return serializer(field, name, value)

    def _default_serializer(field, name, value):
        return str(value)


class PprintItemExporter(BaseItemExporter):

    def __init__(self, file):
        super(PprintItemExporter, self).__init__()
        self.file = file

    def export(self, item):
        self.file.write(pprint.pformat(dict(item)) + '\n')


class PickleItemExporter(BaseItemExporter):

    def __init__(self, *args, **kwargs):
        super(PickleItemExporter, self).__init__()
        self.pickler = Pickler(*args, **kwargs)

    def export(self, item):
        self.pickler.dump(dict(item))


class CsvItemExporter(BaseItemExporter):

    fields_to_export = ()

    def __init__(self, *args, **kwargs):
        super(CsvItemExporter, self).__init__()
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
                self._export_xml_field(field._field, 'value', v)
        self.xg.startElement(name, {})
        self.xg.characters(self._serialize_field(field, name, value))
        self.xg.endElement(name)


"""
Item Exporters are used to export/serialize items into different formats.
"""

import csv
import pprint
from cPickle import Pickler
from xml.sax.saxutils import XMLGenerator


__all__ = ['BaseItemExporter', 'PprintItemExporter', 'PickleItemExporter', \
    'CsvItemExporter', 'XmlItemExporter']

identity = lambda x: x

class BaseItemExporter(object):

    fields_to_export = None
    export_empty_fields = False

    def export(self, item):
        raise NotImplementedError

    def serialize(self, field, name, value):
        serializer = field.get('serializer', identity)
        return serializer(value)

    def _get_fields_to_export(self, item, default_value=None, include_empty=None):
        """Return the fields to export as a list of tuples (name, value)"""
        if include_empty is None:
            include_empty = self.export_empty_fields
        if self.fields_to_export is None:
            if include_empty:
                field_iter = item.fields.iterkeys()
            else:
                field_iter = item.iterkeys()
        else:
            if include_empty:
                field_iter = self.fields_to_export
            else:
                nonempty_fields = set(item.keys())
                field_iter = (x for x in self.fields_to_export if x in \
                    nonempty_fields)
        return [(k, item.get(k, default_value)) for k in field_iter]

    def close(self):
        pass


class XmlItemExporter(BaseItemExporter):

    item_element = 'item'
    root_element = 'items'

    def __init__(self, file):
        super(XmlItemExporter, self).__init__()
        self.xg = XMLGenerator(file)
        self.xg.startDocument()
        self.xg.startElement(self.root_element, {})

    def export(self, item):
        self.xg.startElement(self.item_element, {})
        for field, value in self._get_fields_to_export(item, default_value=''):
            self._export_xml_field(item.fields[field], field, value)

    def close(self):
        self.xg.endElement(self.root_element)
        self.xg.endDocument()

    def _export_xml_field(self, field, name, value):
        self.xg.startElement(name, {})
        if value is not None:
            self.xg.characters(self.serialize(field, name, value))
        self.xg.endElement(name)


class CsvItemExporter(BaseItemExporter):

    include_headers_line = False

    def __init__(self, *args, **kwargs):
        super(CsvItemExporter, self).__init__()
        self.csv_writer = csv.writer(*args, **kwargs)
        if self.include_headers_line:
            if not self.fields_to_export:
                raise RuntimeError("To use include_headers_line you must " \
                    "define fields_to_export attribute")
            self.csv_writer.writerow(self.fields_to_export)

    def export(self, item):
        fields = self._get_fields_to_export(item, default_value='', \
            include_empty=True)
        values = [x[1] for x in fields]
        self.csv_writer.writerow(values)


class PickleItemExporter(BaseItemExporter):

    def __init__(self, *args, **kwargs):
        super(PickleItemExporter, self).__init__()
        self.pickler = Pickler(*args, **kwargs)

    def export(self, item):
        self.pickler.dump(dict(self._get_fields_to_export(item)))


class PprintItemExporter(BaseItemExporter):

    def __init__(self, file):
        super(PprintItemExporter, self).__init__()
        self.file = file

    def export(self, item):
        itemdict = dict(self._get_fields_to_export(item))
        self.file.write(pprint.pformat(itemdict) + '\n')

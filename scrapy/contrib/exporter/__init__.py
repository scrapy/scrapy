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

    def __init__(self, **kwargs):
        self._configure(kwargs)

    def _configure(self, options, dont_fail=False):
        """Configure the exporter by poping options from the ``options`` dict.
        If dont_fail is set, it won't raise an exception on unexpected options
        (useful for using with keyword arguments in subclasses constructors)
        """
        self.fields_to_export = options.pop('fields_to_export', None)
        self.export_empty_fields = options.pop('export_empty_fields', False)
        self.encoding = options.pop('encoding', 'utf-8')
        if not dont_fail and options:
            raise TypeError("Unexpected options: %s" % ', '.join(options.keys()))

    def export_item(self, item):
        raise NotImplementedError

    def serialize_field(self, field, name, value):
        serializer = field.get('serializer', self._to_str_if_unicode)
        return serializer(value)

    def start_exporting(self):
        pass

    def finish_exporting(self):
        pass

    def _to_str_if_unicode(self, value):
        return value.encode(self.encoding) if isinstance(value, unicode) else value

    def _get_serialized_fields(self, item, default_value=None, include_empty=None):
        """Return the fields to export as an iterable of tuples (name,
        serialized_value)
        """
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
        for field_name in field_iter:
            if field_name in item:
                field = item.fields[field_name]
                value = self.serialize_field(field, field_name, item[field_name])
            else:
                value = default_value

            yield field_name, value


class XmlItemExporter(BaseItemExporter):

    def __init__(self, file, **kwargs):
        self.item_element = kwargs.pop('item_element', 'item')
        self.root_element = kwargs.pop('root_element', 'items')
        self._configure(kwargs)
        self.xg = XMLGenerator(file, encoding=self.encoding)

    def start_exporting(self):
        self.xg.startDocument()
        self.xg.startElement(self.root_element, {})

    def export_item(self, item):
        self.xg.startElement(self.item_element, {})
        for name, value in self._get_serialized_fields(item, default_value=''):
            self._export_xml_field(name, value)
        self.xg.endElement(self.item_element)

    def finish_exporting(self):
        self.xg.endElement(self.root_element)
        self.xg.endDocument()

    def _export_xml_field(self, name, serialized_value):
        self.xg.startElement(name, {})
        self.xg.characters(serialized_value)
        self.xg.endElement(name)


class CsvItemExporter(BaseItemExporter):

    def __init__(self, file, include_headers_line=True, **kwargs):
        self._configure(kwargs, dont_fail=True)
        self.include_headers_line = include_headers_line
        self.csv_writer = csv.writer(file, **kwargs)
        self._headers_written = False

    def export_item(self, item):
        self._write_headers_and_set_fields_to_export(item)
        fields = self._get_serialized_fields(item, default_value='', \
            include_empty=True)
        values = [x[1] for x in fields]
        self.csv_writer.writerow(values)

    def _write_headers_and_set_fields_to_export(self, item):
        if self._headers_written:
            return
        self._headers_written = True
        if not self.include_headers_line:
            return
        if not self.fields_to_export:
            self.fields_to_export = item.fields.keys()
        self.csv_writer.writerow(self.fields_to_export)


class PickleItemExporter(BaseItemExporter):

    def __init__(self, file, protocol=0, **kwargs):
        self._configure(kwargs)
        self.pickler = Pickler(file, protocol)

    def export_item(self, item):
        self.pickler.dump(dict(self._get_serialized_fields(item)))


class PprintItemExporter(BaseItemExporter):

    def __init__(self, file, **kwargs):
        self._configure(kwargs)
        self.file = file

    def export_item(self, item):
        itemdict = dict(self._get_serialized_fields(item))
        self.file.write(pprint.pformat(itemdict) + '\n')

"""
Item Exporters are used to export/serialize items into different formats.
"""

import csv
import io
import sys
import pprint
import marshal
import six
from six.moves import cPickle as pickle
from xml.sax.saxutils import XMLGenerator

from scrapy.utils.serialize import ScrapyJSONEncoder
from scrapy.utils.python import to_bytes, to_unicode, to_native_str, is_listlike
from scrapy.item import BaseItem
from scrapy.exceptions import ScrapyDeprecationWarning
import warnings


__all__ = ['BaseItemExporter', 'PprintItemExporter', 'PickleItemExporter',
           'CsvItemExporter', 'XmlItemExporter', 'JsonLinesItemExporter',
           'JsonItemExporter', 'MarshalItemExporter']


class BaseItemExporter(object):

    def __init__(self, **kwargs):
        self._configure(kwargs)

    def _configure(self, options, dont_fail=False):
        """Configure the exporter by poping options from the ``options`` dict.
        If dont_fail is set, it won't raise an exception on unexpected options
        (useful for using with keyword arguments in subclasses constructors)
        """
        self.encoding = options.pop('encoding', None)
        self.fields_to_export = options.pop('fields_to_export', None)
        self.export_empty_fields = options.pop('export_empty_fields', False)
        if not dont_fail and options:
            raise TypeError("Unexpected options: %s" % ', '.join(options.keys()))

    def export_item(self, item):
        raise NotImplementedError

    def serialize_field(self, field, name, value):
        serializer = field.get('serializer', lambda x: x)
        return serializer(value)

    def start_exporting(self):
        pass

    def finish_exporting(self):
        pass

    def _get_serialized_fields(self, item, default_value=None, include_empty=None):
        """Return the fields to export as an iterable of tuples
        (name, serialized_value)
        """
        if include_empty is None:
            include_empty = self.export_empty_fields
        if self.fields_to_export is None:
            if include_empty and not isinstance(item, dict):
                field_iter = six.iterkeys(item.fields)
            else:
                field_iter = six.iterkeys(item)
        else:
            if include_empty:
                field_iter = self.fields_to_export
            else:
                field_iter = (x for x in self.fields_to_export if x in item)

        for field_name in field_iter:
            if field_name in item:
                field = {} if isinstance(item, dict) else item.fields[field_name]
                value = self.serialize_field(field, field_name, item[field_name])
            else:
                value = default_value

            yield field_name, value


class JsonLinesItemExporter(BaseItemExporter):

    def __init__(self, file, **kwargs):
        self._configure(kwargs, dont_fail=True)
        self.file = file
        kwargs.setdefault('ensure_ascii', not self.encoding)
        self.encoder = ScrapyJSONEncoder(**kwargs)

    def export_item(self, item):
        itemdict = dict(self._get_serialized_fields(item))
        data = self.encoder.encode(itemdict) + '\n'
        self.file.write(to_bytes(data, self.encoding))


class JsonItemExporter(BaseItemExporter):

    def __init__(self, file, **kwargs):
        self._configure(kwargs, dont_fail=True)
        self.file = file
        kwargs.setdefault('ensure_ascii', not self.encoding)
        self.encoder = ScrapyJSONEncoder(**kwargs)
        self.first_item = True

    def start_exporting(self):
        self.file.write(b"[\n")

    def finish_exporting(self):
        self.file.write(b"\n]")

    def export_item(self, item):
        if self.first_item:
            self.first_item = False
        else:
            self.file.write(b',\n')
        itemdict = dict(self._get_serialized_fields(item))
        data = self.encoder.encode(itemdict)
        self.file.write(to_bytes(data, self.encoding))


class XmlItemExporter(BaseItemExporter):

    def __init__(self, file, **kwargs):
        self.item_element = kwargs.pop('item_element', 'item')
        self.root_element = kwargs.pop('root_element', 'items')
        self._configure(kwargs)
        if not self.encoding:
            self.encoding = 'utf-8'
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
        if hasattr(serialized_value, 'items'):
            for subname, value in serialized_value.items():
                self._export_xml_field(subname, value)
        elif is_listlike(serialized_value):
            for value in serialized_value:
                self._export_xml_field('value', value)
        elif isinstance(serialized_value, six.text_type):
            self._xg_characters(serialized_value)
        else:
            self._xg_characters(str(serialized_value))
        self.xg.endElement(name)

    # Workaround for http://bugs.python.org/issue17606
    # Before Python 2.7.4 xml.sax.saxutils required bytes;
    # since 2.7.4 it requires unicode. The bug is likely to be
    # fixed in 2.7.6, but 2.7.6 will still support unicode,
    # and Python 3.x will require unicode, so ">= 2.7.4" should be fine.
    if sys.version_info[:3] >= (2, 7, 4):
        def _xg_characters(self, serialized_value):
            if not isinstance(serialized_value, six.text_type):
                serialized_value = serialized_value.decode(self.encoding)
            return self.xg.characters(serialized_value)
    else:  # pragma: no cover
        def _xg_characters(self, serialized_value):
            return self.xg.characters(serialized_value)


class CsvItemExporter(BaseItemExporter):

    def __init__(self, file, include_headers_line=True, join_multivalued=',', **kwargs):
        self._configure(kwargs, dont_fail=True)
        if not self.encoding:
            self.encoding = 'utf-8'
        self.include_headers_line = include_headers_line
        self.stream = io.TextIOWrapper(
            file,
            line_buffering=False,
            write_through=True,
            encoding=self.encoding
        ) if six.PY3 else file
        self.csv_writer = csv.writer(self.stream, **kwargs)
        self._headers_not_written = True
        self._join_multivalued = join_multivalued

    def serialize_field(self, field, name, value):
        serializer = field.get('serializer', self._join_if_needed)
        return serializer(value)

    def _join_if_needed(self, value):
        if isinstance(value, (list, tuple)):
            try:
                return self._join_multivalued.join(value)
            except TypeError:  # list in value may not contain strings
                pass
        return value

    def export_item(self, item):
        if self._headers_not_written:
            self._headers_not_written = False
            self._write_headers_and_set_fields_to_export(item)

        fields = self._get_serialized_fields(item, default_value='',
                                             include_empty=True)
        values = list(self._build_row(x for _, x in fields))
        self.csv_writer.writerow(values)

    def _build_row(self, values):
        for s in values:
            try:
                yield to_native_str(s, self.encoding)
            except TypeError:
                yield s

    def _write_headers_and_set_fields_to_export(self, item):
        if self.include_headers_line:
            if not self.fields_to_export:
                if isinstance(item, dict):
                    # for dicts try using fields of the first item
                    self.fields_to_export = list(item.keys())
                else:
                    # use fields declared in Item
                    self.fields_to_export = list(item.fields.keys())
            row = list(self._build_row(self.fields_to_export))
            self.csv_writer.writerow(row)


class PickleItemExporter(BaseItemExporter):

    def __init__(self, file, protocol=2, **kwargs):
        self._configure(kwargs)
        self.file = file
        self.protocol = protocol

    def export_item(self, item):
        d = dict(self._get_serialized_fields(item))
        pickle.dump(d, self.file, self.protocol)


class MarshalItemExporter(BaseItemExporter):

    def __init__(self, file, **kwargs):
        self._configure(kwargs)
        self.file = file

    def export_item(self, item):
        marshal.dump(dict(self._get_serialized_fields(item)), self.file)


class PprintItemExporter(BaseItemExporter):

    def __init__(self, file, **kwargs):
        self._configure(kwargs)
        self.file = file

    def export_item(self, item):
        itemdict = dict(self._get_serialized_fields(item))
        self.file.write(to_bytes(pprint.pformat(itemdict) + '\n'))


class PythonItemExporter(BaseItemExporter):
    """The idea behind this exporter is to have a mechanism to serialize items
    to built-in python types so any serialization library (like
    json, msgpack, binc, etc) can be used on top of it. Its main goal is to
    seamless support what BaseItemExporter does plus nested items.
    """
    def _configure(self, options, dont_fail=False):
        self.binary = options.pop('binary', True)
        super(PythonItemExporter, self)._configure(options, dont_fail)
        if self.binary:
            warnings.warn(
                "PythonItemExporter will drop support for binary export in the future",
                ScrapyDeprecationWarning)
        if not self.encoding:
            self.encoding = 'utf-8'

    def serialize_field(self, field, name, value):
        serializer = field.get('serializer', self._serialize_value)
        return serializer(value)

    def _serialize_value(self, value):
        if isinstance(value, BaseItem):
            return self.export_item(value)
        if isinstance(value, dict):
            return dict(self._serialize_dict(value))
        if is_listlike(value):
            return [self._serialize_value(v) for v in value]
        encode_func = to_bytes if self.binary else to_unicode
        if isinstance(value, (six.text_type, bytes)):
            return encode_func(value, encoding=self.encoding)
        return value

    def _serialize_dict(self, value):
        for key, val in six.iteritems(value):
            key = to_bytes(key) if self.binary else key
            yield key, self._serialize_value(val)

    def export_item(self, item):
        result = dict(self._get_serialized_fields(item))
        if self.binary:
            result = dict(self._serialize_dict(result))
        return result

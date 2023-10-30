"""
Item Exporters are used to export/serialize items into different formats.
"""

import csv
import io
import marshal
import pickle
import pprint
from collections.abc import Mapping
from xml.sax.saxutils import XMLGenerator

from itemadapter import ItemAdapter, is_item

from scrapy.item import Item
from scrapy.utils.python import is_listlike, to_bytes, to_unicode
from scrapy.utils.serialize import ScrapyJSONEncoder

__all__ = [
    "BaseItemExporter",
    "PprintItemExporter",
    "PickleItemExporter",
    "CsvItemExporter",
    "XmlItemExporter",
    "JsonLinesItemExporter",
    "JsonItemExporter",
    "MarshalItemExporter",
]


class BaseItemExporter:
    def __init__(self, *, dont_fail=False, **kwargs):
        self._kwargs = kwargs
        self._configure(kwargs, dont_fail=dont_fail)

    def _configure(self, options, dont_fail=False):
        """Configure the exporter by popping options from the ``options`` dict.
        If dont_fail is set, it won't raise an exception on unexpected options
        (useful for using with keyword arguments in subclasses ``__init__`` methods)
        """
        self.encoding = options.pop("encoding", None)
        self.fields_to_export = options.pop("fields_to_export", None)
        self.export_empty_fields = options.pop("export_empty_fields", False)
        self.indent = options.pop("indent", None)
        if not dont_fail and options:
            raise TypeError(f"Unexpected options: {', '.join(options.keys())}")

    def export_item(self, item):
        raise NotImplementedError

    def serialize_field(self, field, name, value):
        serializer = field.get("serializer", lambda x: x)
        return serializer(value)

    def start_exporting(self):
        pass

    def finish_exporting(self):
        pass

    def _get_serialized_fields(self, item, default_value=None, include_empty=None):
        """Return the fields to export as an iterable of tuples
        (name, serialized_value)
        """
        item = ItemAdapter(item)

        if include_empty is None:
            include_empty = self.export_empty_fields

        if self.fields_to_export is None:
            if include_empty:
                field_iter = item.field_names()
            else:
                field_iter = item.keys()
        elif isinstance(self.fields_to_export, Mapping):
            if include_empty:
                field_iter = self.fields_to_export.items()
            else:
                field_iter = (
                    (x, y) for x, y in self.fields_to_export.items() if x in item
                )
        else:
            if include_empty:
                field_iter = self.fields_to_export
            else:
                field_iter = (x for x in self.fields_to_export if x in item)

        for field_name in field_iter:
            if isinstance(field_name, str):
                item_field, output_field = field_name, field_name
            else:
                item_field, output_field = field_name
            if item_field in item:
                field_meta = item.get_field_meta(item_field)
                value = self.serialize_field(field_meta, output_field, item[item_field])
            else:
                value = default_value

            yield output_field, value


class JsonLinesItemExporter(BaseItemExporter):
    def __init__(self, file, **kwargs):
        super().__init__(dont_fail=True, **kwargs)
        self.file = file
        self._kwargs.setdefault("ensure_ascii", not self.encoding)
        self.encoder = ScrapyJSONEncoder(**self._kwargs)

    def export_item(self, item):
        itemdict = dict(self._get_serialized_fields(item))
        data = self.encoder.encode(itemdict) + "\n"
        self.file.write(to_bytes(data, self.encoding))


class JsonItemExporter(BaseItemExporter):
    def __init__(self, file, **kwargs):
        super().__init__(dont_fail=True, **kwargs)
        self.file = file
        # there is a small difference between the behaviour or JsonItemExporter.indent
        # and ScrapyJSONEncoder.indent. ScrapyJSONEncoder.indent=None is needed to prevent
        # the addition of newlines everywhere
        json_indent = (
            self.indent if self.indent is not None and self.indent > 0 else None
        )
        self._kwargs.setdefault("indent", json_indent)
        self._kwargs.setdefault("ensure_ascii", not self.encoding)
        self.encoder = ScrapyJSONEncoder(**self._kwargs)
        self.first_item = True

    def _beautify_newline(self):
        if self.indent is not None:
            self.file.write(b"\n")

    def _add_comma_after_first(self):
        if self.first_item:
            self.first_item = False
        else:
            self.file.write(b",")
            self._beautify_newline()

    def start_exporting(self):
        self.file.write(b"[")
        self._beautify_newline()

    def finish_exporting(self):
        self._beautify_newline()
        self.file.write(b"]")

    def export_item(self, item):
        itemdict = dict(self._get_serialized_fields(item))
        data = to_bytes(self.encoder.encode(itemdict), self.encoding)
        self._add_comma_after_first()
        self.file.write(data)


class XmlItemExporter(BaseItemExporter):
    def __init__(self, file, **kwargs):
        self.item_element = kwargs.pop("item_element", "item")
        self.root_element = kwargs.pop("root_element", "items")
        super().__init__(**kwargs)
        if not self.encoding:
            self.encoding = "utf-8"
        self.xg = XMLGenerator(file, encoding=self.encoding)

    def _beautify_newline(self, new_item=False):
        if self.indent is not None and (self.indent > 0 or new_item):
            self.xg.characters("\n")

    def _beautify_indent(self, depth=1):
        if self.indent:
            self.xg.characters(" " * self.indent * depth)

    def start_exporting(self):
        self.xg.startDocument()
        self.xg.startElement(self.root_element, {})
        self._beautify_newline(new_item=True)

    def export_item(self, item):
        self._beautify_indent(depth=1)
        self.xg.startElement(self.item_element, {})
        self._beautify_newline()
        for name, value in self._get_serialized_fields(item, default_value=""):
            self._export_xml_field(name, value, depth=2)
        self._beautify_indent(depth=1)
        self.xg.endElement(self.item_element)
        self._beautify_newline(new_item=True)

    def finish_exporting(self):
        self.xg.endElement(self.root_element)
        self.xg.endDocument()

    def _export_xml_field(self, name, serialized_value, depth):
        self._beautify_indent(depth=depth)
        self.xg.startElement(name, {})
        if hasattr(serialized_value, "items"):
            self._beautify_newline()
            for subname, value in serialized_value.items():
                self._export_xml_field(subname, value, depth=depth + 1)
            self._beautify_indent(depth=depth)
        elif is_listlike(serialized_value):
            self._beautify_newline()
            for value in serialized_value:
                self._export_xml_field("value", value, depth=depth + 1)
            self._beautify_indent(depth=depth)
        elif isinstance(serialized_value, str):
            self.xg.characters(serialized_value)
        else:
            self.xg.characters(str(serialized_value))
        self.xg.endElement(name)
        self._beautify_newline()


class CsvItemExporter(BaseItemExporter):
    def __init__(
        self,
        file,
        include_headers_line=True,
        join_multivalued=",",
        errors=None,
        **kwargs,
    ):
        super().__init__(dont_fail=True, **kwargs)
        if not self.encoding:
            self.encoding = "utf-8"
        self.include_headers_line = include_headers_line
        self.stream = io.TextIOWrapper(
            file,
            line_buffering=False,
            write_through=True,
            encoding=self.encoding,
            newline="",  # Windows needs this https://github.com/scrapy/scrapy/issues/3034
            errors=errors,
        )
        self.csv_writer = csv.writer(self.stream, **self._kwargs)
        self._headers_not_written = True
        self._join_multivalued = join_multivalued

    def serialize_field(self, field, name, value):
        serializer = field.get("serializer", self._join_if_needed)
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

        fields = self._get_serialized_fields(item, default_value="", include_empty=True)
        values = list(self._build_row(x for _, x in fields))
        self.csv_writer.writerow(values)

    def finish_exporting(self):
        self.stream.detach()  # Avoid closing the wrapped file.

    def _build_row(self, values):
        for s in values:
            try:
                yield to_unicode(s, self.encoding)
            except TypeError:
                yield s

    def _write_headers_and_set_fields_to_export(self, item):
        if self.include_headers_line:
            if not self.fields_to_export:
                # use declared field names, or keys if the item is a dict
                self.fields_to_export = ItemAdapter(item).field_names()
            if isinstance(self.fields_to_export, Mapping):
                fields = self.fields_to_export.values()
            else:
                fields = self.fields_to_export
            row = list(self._build_row(fields))
            self.csv_writer.writerow(row)


class PickleItemExporter(BaseItemExporter):
    def __init__(self, file, protocol=4, **kwargs):
        super().__init__(**kwargs)
        self.file = file
        self.protocol = protocol

    def export_item(self, item):
        d = dict(self._get_serialized_fields(item))
        pickle.dump(d, self.file, self.protocol)


class MarshalItemExporter(BaseItemExporter):
    """Exports items in a Python-specific binary format (see
    :mod:`marshal`).

    :param file: The file-like object to use for exporting the data. Its
                 ``write`` method should accept :class:`bytes` (a disk file
                 opened in binary mode, a :class:`~io.BytesIO` object, etc)
    """

    def __init__(self, file, **kwargs):
        super().__init__(**kwargs)
        self.file = file

    def export_item(self, item):
        marshal.dump(dict(self._get_serialized_fields(item)), self.file)


class PprintItemExporter(BaseItemExporter):
    def __init__(self, file, **kwargs):
        super().__init__(**kwargs)
        self.file = file

    def export_item(self, item):
        itemdict = dict(self._get_serialized_fields(item))
        self.file.write(to_bytes(pprint.pformat(itemdict) + "\n"))


class PythonItemExporter(BaseItemExporter):
    """This is a base class for item exporters that extends
    :class:`BaseItemExporter` with support for nested items.

    It serializes items to built-in Python types, so that any serialization
    library (e.g. :mod:`json` or msgpack_) can be used on top of it.

    .. _msgpack: https://pypi.org/project/msgpack/
    """

    def _configure(self, options, dont_fail=False):
        super()._configure(options, dont_fail)
        if not self.encoding:
            self.encoding = "utf-8"

    def serialize_field(self, field, name, value):
        serializer = field.get("serializer", self._serialize_value)
        return serializer(value)

    def _serialize_value(self, value):
        if isinstance(value, Item):
            return self.export_item(value)
        if is_item(value):
            return dict(self._serialize_item(value))
        if is_listlike(value):
            return [self._serialize_value(v) for v in value]
        if isinstance(value, (str, bytes)):
            return to_unicode(value, encoding=self.encoding)
        return value

    def _serialize_item(self, item):
        for key, value in ItemAdapter(item).items():
            yield key, self._serialize_value(value)

    def export_item(self, item):
        result = dict(self._get_serialized_fields(item))
        return result

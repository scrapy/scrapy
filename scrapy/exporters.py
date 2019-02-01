""":ref:`Item exporters <topics-exporters>` are used to export/serialize items
into different formats.

The item exporters below are bundled with Scrapy. Some of them contain output
examples, which assume you're exporting these two items::

    Item(name='Color TV', price='1200')
    Item(name='DVD player', price='200')
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
    """This is the (abstract) base class for all Item Exporters. It provides
   support for common features used by all (concrete) Item Exporters, such as
   defining what fields to export, whether to export empty fields, or which
   encoding to use.

   These features can be configured through the constructor arguments which
   populate their respective instance attributes: :attr:`fields_to_export`,
   :attr:`export_empty_fields`, :attr:`encoding`, :attr:`indent`.
   """

    def __init__(self, **kwargs):
        #: The encoding that will be used to encode unicode values. This only
        #: affects unicode values (which are always serialized to str using
        #: this encoding). Other value types are passed unchanged to the
        #: specific serialization library.
        self.encoding = None

        #: A list with the name of the fields that will be exported, or None if
        #: you want to export all fields. Defaults to None.
        #:
        #: Some exporters (like :class:`CsvItemExporter`) respect the order of
        #: the fields defined in this attribute.
        #:
        #: Some exporters may require fields_to_export list in order to export
        #: the data properly when spiders return dicts (not :class:`~Item`
        #: instances).
        self.fields_to_export = None

        #: Whether to include empty/unpopulated item fields in the exported
        #: data.
        #:
        #: Defaults to ``False``. Some exporters (like
        #: :class:`CsvItemExporter`) ignore this attribute and always export
        #: all empty fields.
        #:
        #: This option is ignored for dict items.
        self.export_empty_fields = None

        #: Amount of spaces used to indent the output on each level. Defaults
        #: to ``0``.
        #:
        #: * ``indent=None`` selects the most compact representation,
        #:   all items in the same line with no indentation
        #: * ``indent<=0`` each item on its own line, no indentation
        #: * ``indent>0`` each item on its own line, indented with the provided
        #:   numeric value
        self.indent = None
        self._configure(kwargs)

    def _configure(self, options, dont_fail=False):
        """Configure the exporter by poping options from the ``options`` dict.
        If dont_fail is set, it won't raise an exception on unexpected options
        (useful for using with keyword arguments in subclasses constructors)
        """
        self.encoding = options.pop('encoding', None)
        self.fields_to_export = options.pop('fields_to_export', None)
        self.export_empty_fields = options.pop('export_empty_fields', False)
        self.indent = options.pop('indent', None)
        if not dont_fail and options:
            raise TypeError("Unexpected options: %s" % ', '.join(options.keys()))

    def export_item(self, item):
        """Exports the given item. This method must be implemented in
        subclasses."""
        raise NotImplementedError

    def serialize_field(self, field, name, value):
        """Return the serialized value for the given field. You can override this
        method (in your custom Item Exporters) if you want to control how a
        particular field or value will be serialized/exported.

        By default, this method looks for a serializer :ref:`declared in the item
        field <topics-exporters-serializers>` and returns the result of applying
        that serializer to the value. If no serializer is found, it returns the
        value unchanged except for ``unicode`` values which are encoded to
        ``str`` using the encoding declared in the :attr:`encoding` attribute.

        :param field: the field being serialized. If a raw dict is being
                      exported (not :class:`~.Item`) *field* value is an empty
                      dict.
        :type field: :class:`~scrapy.item.Field` object or an empty dict

        :param name: the name of the field being serialized
        :type name: str

        :param value: the value being serialized
        """
        serializer = field.get('serializer', lambda x: x)
        return serializer(value)

    def start_exporting(self):
        """Signal the beginning of the exporting process. Some exporters may use
        this to generate some required header (for example, the
        :class:`XmlItemExporter`). You must call this method before exporting any
        items."""
        pass

    def finish_exporting(self):
        """Signal the end of the exporting process. Some exporters may use this to
        generate some required footer (for example, the
        :class:`XmlItemExporter`). You must always call this method after you
        have no more items to export."""
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
    """Exports Items in JSON format to the specified file-like object, writing one
    JSON-encoded item per line. The additional constructor arguments are passed
    to the :class:`BaseItemExporter` constructor, and the leftover arguments to
    the `JSONEncoder`_ constructor, so you can use any `JSONEncoder`_
    constructor argument to customize this exporter.

    :param file: the file-like object to use for exporting the data. Its ``write`` method should
                 accept ``bytes`` (a disk file opened in binary mode, a ``io.BytesIO`` object, etc)

    A typical output of this exporter would be:

    .. code-block:: javascript

        {"name": "Color TV", "price": "1200"}
        {"name": "DVD player", "price": "200"}

    Unlike the one produced by :class:`JsonItemExporter`, the format produced by
    this exporter is well suited for serializing large amounts of data.

    .. _JSONEncoder: https://docs.python.org/2/library/json.html#json.JSONEncoder
    """

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
    """Exports Items in JSON format to the specified file-like object, writing all
    objects as a list of objects. The additional constructor arguments are
    passed to the :class:`BaseItemExporter` constructor, and the leftover
    arguments to the `JSONEncoder`_ constructor, so you can use any
    `JSONEncoder`_ constructor argument to customize this exporter.

    :param file: the file-like object to use for exporting the data. Its ``write`` method should
                 accept ``bytes`` (a disk file opened in binary mode, a ``io.BytesIO`` object, etc)

    A typical output of this exporter would be:

    .. code-block:: javascript

        [{"name": "Color TV", "price": "1200"},
        {"name": "DVD player", "price": "200"}]

    .. _json-with-large-data:

    .. warning:: JSON is very simple and flexible serialization format, but it
        doesn't scale well for large amounts of data since incremental (aka.
        stream-mode) parsing is not well supported (if at all) among JSON parsers
        (on any language), and most of them just parse the entire object in
        memory. If you want the power and simplicity of JSON with a more
        stream-friendly format, consider using :class:`JsonLinesItemExporter`
        instead, or splitting the output in multiple chunks.

    .. _JSONEncoder: https://docs.python.org/2/library/json.html#json.JSONEncoder
    """

    def __init__(self, file, **kwargs):
        self._configure(kwargs, dont_fail=True)
        self.file = file
        # there is a small difference between the behaviour or JsonItemExporter.indent
        # and ScrapyJSONEncoder.indent. ScrapyJSONEncoder.indent=None is needed to prevent
        # the addition of newlines everywhere
        json_indent = self.indent if self.indent is not None and self.indent > 0 else None
        kwargs.setdefault('indent', json_indent)
        kwargs.setdefault('ensure_ascii', not self.encoding)
        self.encoder = ScrapyJSONEncoder(**kwargs)
        self.first_item = True

    def _beautify_newline(self):
        if self.indent is not None:
            self.file.write(b'\n')

    def start_exporting(self):
        self.file.write(b"[")
        self._beautify_newline()

    def finish_exporting(self):
        self._beautify_newline()
        self.file.write(b"]")

    def export_item(self, item):
        if self.first_item:
            self.first_item = False
        else:
            self.file.write(b',')
            self._beautify_newline()
        itemdict = dict(self._get_serialized_fields(item))
        data = self.encoder.encode(itemdict)
        self.file.write(to_bytes(data, self.encoding))


class XmlItemExporter(BaseItemExporter):
    """Exports Items in XML format to the specified file object.

    :param file: the file-like object to use for exporting the data. Its
                 ``write`` method should accept ``bytes`` (a disk file opened
                 in binary mode, a ``io.BytesIO`` object, etc)

    :param root_element: The name of root element in the exported XML.
    :type root_element: str

    :param item_element: The name of each item element in the exported XML.
    :type item_element: str

    The additional keyword arguments of this constructor are passed to the
    :class:`BaseItemExporter` constructor.

    A typical output of this exporter would be:

    .. code-block:: xml

        <?xml version="1.0" encoding="utf-8"?>
        <items>
            <item>
                <name>Color TV</name>
                <price>1200</price>
            </item>
            <item>
                <name>DVD player</name>
                <price>200</price>
            </item>
        </items>

    Unless overridden in the :meth:`serialize_field` method, multi-valued fields are
    exported by serializing each value inside a ``<value>`` element. This is for
    convenience, as multi-valued fields are very common.

    For example, the item::

        Item(name=['John', 'Doe'], age='23')

    Would be serialized as:

    .. code-block:: xml

        <?xml version="1.0" encoding="utf-8"?>
        <items>
            <item>
                <name>
                    <value>John</value>
                    <value>Doe</value>
                </name>
                <age>23</age>
            </item>
        </items>
    """

    def __init__(self, file, **kwargs):
        self.item_element = kwargs.pop('item_element', 'item')
        self.root_element = kwargs.pop('root_element', 'items')
        self._configure(kwargs)
        if not self.encoding:
            self.encoding = 'utf-8'
        self.xg = XMLGenerator(file, encoding=self.encoding)

    def _beautify_newline(self, new_item=False):
        if self.indent is not None and (self.indent > 0 or new_item):
            self._xg_characters('\n')

    def _beautify_indent(self, depth=1):
        if self.indent:
            self._xg_characters(' ' * self.indent * depth)

    def start_exporting(self):
        self.xg.startDocument()
        self.xg.startElement(self.root_element, {})
        self._beautify_newline(new_item=True)

    def export_item(self, item):
        self._beautify_indent(depth=1)
        self.xg.startElement(self.item_element, {})
        self._beautify_newline()
        for name, value in self._get_serialized_fields(item, default_value=''):
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
        if hasattr(serialized_value, 'items'):
            self._beautify_newline()
            for subname, value in serialized_value.items():
                self._export_xml_field(subname, value, depth=depth+1)
            self._beautify_indent(depth=depth)
        elif is_listlike(serialized_value):
            self._beautify_newline()
            for value in serialized_value:
                self._export_xml_field('value', value, depth=depth+1)
            self._beautify_indent(depth=depth)
        elif isinstance(serialized_value, six.text_type):
            self._xg_characters(serialized_value)
        else:
            self._xg_characters(str(serialized_value))
        self.xg.endElement(name)
        self._beautify_newline()

    # Workaround for https://bugs.python.org/issue17606
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
    """Exports Items in CSV format to the given file-like object. If the
    :attr:`fields_to_export` attribute is set, it will be used to define the
    CSV columns and their order. The :attr:`export_empty_fields` attribute has
    no effect on this exporter.

    :param file: the file-like object to use for exporting the data. Its ``write`` method should
                 accept ``bytes`` (a disk file opened in binary mode, a ``io.BytesIO`` object, etc)

    :param include_headers_line: If enabled, makes the exporter output a header
        line with the field names taken from
        :attr:`BaseItemExporter.fields_to_export` or the first exported item fields.
    :type include_headers_line: boolean

    :param join_multivalued: The char (or chars) that will be used for joining
        multi-valued fields, if found.
    :type include_headers_line: str

    The additional keyword arguments of this constructor are passed to the
    :class:`BaseItemExporter` constructor, and the leftover arguments to the
    `csv.writer`_ constructor, so you can use any `csv.writer` constructor
    argument to customize this exporter.

    A typical output of this exporter would be::

        product,price
        Color TV,1200
        DVD player,200

    .. _csv.writer: https://docs.python.org/2/library/csv.html#csv.writer
    """

    def __init__(self, file, include_headers_line=True, join_multivalued=',', **kwargs):
        self._configure(kwargs, dont_fail=True)
        if not self.encoding:
            self.encoding = 'utf-8'
        self.include_headers_line = include_headers_line
        self.stream = io.TextIOWrapper(
            file,
            line_buffering=False,
            write_through=True,
            encoding=self.encoding,
            newline='' # Windows needs this https://github.com/scrapy/scrapy/issues/3034
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
    """Exports Items in pickle format to the given file-like object.

    :param file: the file-like object to use for exporting the data. Its ``write`` method should
                 accept ``bytes`` (a disk file opened in binary mode, a ``io.BytesIO`` object, etc)

    :param protocol: The pickle protocol to use.
    :type protocol: int

    For more information, refer to the `pickle module documentation`_.

    The additional keyword arguments of this constructor are passed to the
    :class:`BaseItemExporter` constructor.

    Pickle isn't a human readable format, so no output examples are provided.

    .. _pickle module documentation: https://docs.python.org/2/library/pickle.html
    """

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
    """Exports Items in pretty print format to the specified file object.

    :param file: the file-like object to use for exporting the data. Its ``write`` method should
                    accept ``bytes`` (a disk file opened in binary mode, a ``io.BytesIO`` object, etc)

    The additional keyword arguments of this constructor are passed to the
    :class:`BaseItemExporter` constructor.

    A typical output of this exporter would be:

    .. code-block:: javascript

        {'name': 'Color TV', 'price': '1200'}
        {'name': 'DVD player', 'price': '200'}

    Longer lines (when present) are pretty-formatted.
    """

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

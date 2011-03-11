"""
Extended types for IBL extraction
"""
from itertools import chain 

from scrapy.contrib.ibl.extractors import text, html

class FieldDescriptor(object):
    """description of a scraped attribute"""
    __slots__ = ('name', 'description', 'extractor', 'required')

    def __init__(self, name, description, extractor=text, required=False):
        self.name = name
        self.description = description
        self.extractor = extractor
        self.required = required
    
    @classmethod
    def from_field(cls, name, field):
        return cls(name, field.get('description'), \
            field.get('ibl_extractor', text), field.get('required', False))

    def __str__(self):
        return "FieldDescriptor(%s)" % self.name

class ItemDescriptor(object):
    """Simple auto scraping item descriptor. 

    This used to describe type-specific operations and may be overridden where
    necessary.
    """

    def __init__(self, name, description, attribute_descriptors):
        self.name = name
        self.attribute_map = dict((d.name, d) for d in attribute_descriptors)
        self._required_attributes = [d.name for d in attribute_descriptors \
                if d.required]

    @classmethod
    def from_item(cls, name, description, item):
        a = [FieldDescriptor.from_field(n, f) for n, f in item.fields.items()]
        return cls(name, description, a)

    def validated(self, data):
        """Only return the items in the data that are valid"""
        return [d for d in data if self._item_validates(d)]

    def _item_validates(self, item):
        """simply checks that all mandatory attributes are present"""
        variant_attrs = set(chain(*
            [v.keys() for v in item.get('variants', [])]))
        return all([(name in item or name in variant_attrs) \
                for name in self._required_attributes])

    def get_required_attributes(self):
        return self._required_attributes
    
    def __str__(self):
        return "ItemDescriptor(%s)" % self.name

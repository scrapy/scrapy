"""
Extended types for IBL extraction
"""
from itertools import chain 

from scrapy.contrib.ibl.extractors import text

class FieldDescriptor(object):
    """description of a scraped attribute"""
    __slots__ = ('name', 'description', 'extractor', 'required', 'allow_markup')

    def __init__(self, name, description, extractor=text, required=False,
            allow_markup=False):
        self.name = name
        self.description = description
        self.extractor = extractor
        self.required = required
        self.allow_markup = allow_markup
    
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

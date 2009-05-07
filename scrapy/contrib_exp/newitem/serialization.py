import simplejson

from scrapy.utils.serialization import ScrapyJSONEncoder


def item_to_dict(item):
    """Returns a dict representation of an item"""
    res = {}
    for field in item.fields:
        res[field] = getattr(item, field)
        
    return res


def item_to_json(item):
    """Returns a json representation of an item"""
    return simplejson.dumps(item_to_dict(item), cls=ScrapyJSONEncoder)


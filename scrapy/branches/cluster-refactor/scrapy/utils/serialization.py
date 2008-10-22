"""
This module provides a universal API for different serialization formats.

Keep in mind that not all formats support all types for serialization, and some
formats (like pprint) may be unsafe for unserialization (like pprint) but it
may still very convenient for serialization.
"""

import datetime
import decimal
import cPickle as pickle
import pprint

import simplejson

class ScrapyJSONEncoder(simplejson.JSONEncoder):
    """
    JSONEncoder subclass that knows how to encode date/time and decimal types.
    """

    DATE_FORMAT = "%Y-%m-%d"
    TIME_FORMAT = "%H:%M:%S"

    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.strftime("%s %s" % (self.DATE_FORMAT, self.TIME_FORMAT))
        elif isinstance(o, datetime.date):
            return o.strftime(self.DATE_FORMAT)
        elif isinstance(o, datetime.time):
            return o.strftime(self.TIME_FORMAT)
        elif isinstance(o, decimal.Decimal):
            return str(o)
        else:
            return super(ScrapyJSONEncoder, self).default(o)

serialize_funcs = {
    'json': lambda obj: simplejson.dumps(obj, cls=ScrapyJSONEncoder),
    'pprint': lambda obj: pprint.pformat(obj),
    'pickle': lambda obj: pickle.dumps(obj),
}

unserialize_funcs = {
    'json': lambda text: simplejson.loads(text),
    'pprint': lambda text: eval(text),
    'pickle': lambda text: pickle.loads(text),
}

def serialize(obj, format='pickle'):
    """
    Main entrance point for serialization.

    Supported formats: pickle, json, pprint
    """
    try:
        func = serialize_funcs[format]
        return func(obj)
    except KeyError:
        raise TypeError("Unknown serialization format: %s" % format)

def unserialize(text, format='pickle'):
    """
    Main entrance point for unserialization.
    """
    try:
        func = unserialize_funcs[format]
        return func(text)
    except KeyError:
        raise TypeError("Unknown serialization format: %s" % format)

def parse_jsondatetime(text):
    if isinstance(text, basestring):
        return datetime.datetime.strptime(text, "%s %s" % \
               (ScrapyJSONEncoder.DATE_FORMAT, ScrapyJSONEncoder.TIME_FORMAT))


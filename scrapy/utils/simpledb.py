"""Helper functions for Amazon SimpleDB"""

from datetime import datetime

def to_sdb_value(obj):
    """Convert the given object to proper value to store in Amazon SimpleDB"""
    if isinstance(obj, bool):
        return u'%d' % obj
    elif isinstance(obj, (int, long)):
        return "%016d" % obj
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, basestring):
        return obj
    elif obj is None:
        return u''
    else:
        raise TypeError("Unsupported Type: %s" % type(obj).__name__)


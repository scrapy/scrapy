import datetime
import decimal
import re
import time


class BaseField(object):
    def __init__(self, default=None):
        self._default = self.to_python(default) if default is not None else None

    def to_python(self, value):
        raise NotImplementedError()

    def from_unicode_list(self, unicode_list):
        return self.to_python(unicode_list[0]) if unicode_list else None

    def get_default(self):
        return self._default


class ListField(BaseField):
    def __init__(self, field, default=None):
        self.field = field
        super(ListField, self).__init__(default)

    def to_python(self, value):
        if hasattr(value, '__iter__'):
            return [self.field.to_python(v) for v in value]
        else:
            raise TypeError("Cannot instatiante %s with %s" \
                             % (self.__class__.__name__, type(value).__name__))

    def from_unicode_list(self, unicode_list):
        return self.to_python(unicode_list)


class BooleanField(BaseField):
    def to_python(self, value):
        return bool(value)

    def from_unicode_list(self, unicode_list):
        return self.to_python(unicode_list)


class DateField(BaseField):
    ansi_date_re = re.compile(r'^\d{4}-\d{1,2}-\d{1,2}$')

    def to_python(self, value):
        if isinstance(value, datetime.datetime):
            return value.date()
        elif isinstance(value, datetime.date):
            return value
        elif isinstance(value, basestring):
            if not self.ansi_date_re.search(value):
                raise ValueError("Enter a valid date in YYYY-MM-DD format.")

            year, month, day = map(int, value.split('-'))
            try:
                return datetime.date(year, month, day)
            except ValueError, e:
                raise ValueError("Invalid date: %s" % str(e))
        else:
            raise TypeError("Cannot instatiante %s with %s" \
                             % (self.__class__.__name__, type(value).__name__))


class DateTimeField(BaseField):
    def to_python(self, value):
        if isinstance(value, datetime.datetime):
            return value
        elif isinstance(value, datetime.date):
            return datetime.datetime(value.year, value.month, value.day)
        elif isinstance(value, basestring):
            # Attempt to parse a datetime:
            value = str(value)
            # split usecs, because they are not recognized by strptime.
            if '.' in value:
                try:
                    value, usecs = value.split('.')
                    usecs = int(usecs)
                except ValueError:
                    raise ValueError('Enter a valid date/time in YYYY-MM-DD HH:MM[:ss[.uuuuuu]] format.')
            else:
                usecs = 0
            kwargs = {'microsecond': usecs}
            try: # Seconds are optional, so try converting seconds first.
                return datetime.datetime(*time.strptime(value, '%Y-%m-%d %H:%M:%S')[:6],
                                         **kwargs)

            except ValueError:
                try: # Try without seconds.
                    return datetime.datetime(*time.strptime(value, '%Y-%m-%d %H:%M')[:5],
                                             **kwargs)
                except ValueError: # Try without hour/minutes/seconds.
                    try:
                        return datetime.datetime(*time.strptime(value, '%Y-%m-%d')[:3],
                                                 **kwargs)
                    except ValueError:
                        raise ValueError('Enter a valid date/time in YYYY-MM-DD HH:MM[:ss[.uuuuuu]] format.')
        else:
            raise TypeError("Cannot instatiante %s with %s" \
                             % (self.__class__.__name__, type(value).__name__))



class DecimalField(BaseField):
    def to_python(self, value):
        return decimal.Decimal(value)


class FloatField(BaseField):
    def to_python(self, value):
        return float(value)


class IntegerField(BaseField):
    def to_python(self, value):
        return int(value)


class TextField(BaseField):
    def to_python(self, value):
        if isinstance(value, unicode):
            return value
        elif isinstance(value, (long, float)):
            return unicode(value)
        # Note: True and False are instances of int!
        elif isinstance(value, int) and not isinstance(value, bool): 
            return unicode(value)
        else:
            raise TypeError("%s values cannot be created from '%s' objects" % \
                (self.__class__.__name__, value.__class__.__name__))

    def from_unicode_list(self, unicode_list):
        return u' '.join((self.to_python(x) for x in unicode_list))

class TimeField(BaseField):
    def to_python(self, value):
        if isinstance(value, datetime.time):
            return value
        if isinstance(value, datetime.datetime):
            return value.time
        elif isinstance(value, basestring):
            # Attempt to parse a datetime:
            value = str(value)
            # split usecs, because they are not recognized by strptime.
            if '.' in value:
                try:
                    value, usecs = value.split('.')
                    usecs = int(usecs)
                except ValueError:
                    raise ValueError('Enter a valid time in HH:MM[:ss[.uuuuuu]] format.')
            else:
                usecs = 0
            kwargs = {'microsecond': usecs}

            try: # Seconds are optional, so try converting seconds first.
                return datetime.time(*time.strptime(value, '%H:%M:%S')[3:6],
                                     **kwargs)
            except ValueError:
                try: # Try without seconds.
                    return datetime.time(*time.strptime(value, '%H:%M')[3:5],
                                             **kwargs)
                except ValueError:
                    raise ValueError('Enter a valid time in HH:MM[:ss[.uuuuuu]] format.')
        else:
            raise TypeError("Cannot instatiante %s with %s" \
                             % (self.__class__.__name__, type(value).__name__))

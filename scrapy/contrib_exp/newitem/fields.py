import datetime
import decimal
import re
import time

class BaseField(object):
    def __init__(self, default=None):
        self.default = default or self.to_python(None)

    def to_python(self, value):
        """
        Converts the input value into the expected Python data type.
        Subclasses should override this.
        """
        return value


class MultiValuedField(BaseField):
    def __init__(self, field_type, default=None):
        self._field = field_type()
        super(MultiValuedField, self).__init__(default)

    def to_python(self, value):
        if value is None:
            return []
        else:
            return [self._field.to_python(v) for v in value]


class BooleanField(BaseField):
    def to_python(self, value):
        return bool(value)


class DateField(BaseField):
    ansi_date_re = re.compile(r'^\d{4}-\d{1,2}-\d{1,2}$')

    def to_python(self, value):
        if value is None:
            return value
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value

        if not self.ansi_date_re.search(value):
            raise ValueError("Enter a valid date in YYYY-MM-DD format.")

        year, month, day = map(int, value.split('-'))
        try:
            return datetime.date(year, month, day)
        except ValueError, e:
            raise ValueError("Invalid date: %s" % str(e))


class DateTimeField(BaseField):
    def to_python(self, value):
        if value is None:
            return value
        if isinstance(value, datetime.datetime):
            return value
        if isinstance(value, datetime.date):
            return datetime.datetime(value.year, value.month, value.day)

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


class DecimalField(BaseField):
    def to_python(self, value):
        return decimal.Decimal(value) if value is not None else None


class FloatField(BaseField):
    def to_python(self, value):
        return float(value) if value is not None else None


class IntegerField(BaseField):
    def to_python(self, value):
        return int(value) if value is not None else None


class StringField(BaseField):
    def to_python(self, value):
        if hasattr(value, '__iter__'):
            return self.to_python(self.to_single(value))
        elif isinstance(value, basestring):
            return value
        elif value is None:
            return value
        else:
            raise ValueError("StringField expects a basestring, got %s" \
                % type(value).__name__)

    def to_single(self, value):
        "Converts the input iterable into a single value."
        return ' '.join(value)


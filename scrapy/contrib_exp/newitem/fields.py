import datetime
import decimal
import re
import time


__all__ = ['MultiValuedField', 'BooleanField', 'DateField', 'DateTimeField',
           'DecimalField', 'FloatField', 'IntegerField', 'StringField']


class BaseField(object):
    def __init__(self, required=False, default=None):
        self.required = required
        self.default = default or self.to_python(None)

    def assign(self, value):
        return self.to_python(value)

    def to_python(self, value):
        """
        Converts the input value into the expected Python data type.
        Subclasses should override this.
        """
        return value


class Field(BaseField):
    def assign(self, value):
        if hasattr(value, '__iter__'):
            return self.to_python(self.deiter(value))
        else:
            return self.to_python(value)

    def deiter(self, value):
        "Converts the input iterable into a single value."
        return ' '.join(value)


class MultiValuedField(BaseField):
    def __init__(self, field_type, required=False, default=None):
        self._field = field_type()
        super(MultiValuedField, self).__init__(required, default)

    def to_python(self, value):
        if value is None:
            return []
        else:
            return [self._field.to_python(v) for v in value]


class BooleanField(Field):
    def to_python(self, value):
        return bool(value)


ansi_date_re = re.compile(r'^\d{4}-\d{1,2}-\d{1,2}$')


class DateField(Field):
    def to_python(self, value):
        if value is None:
            return value
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value

        if not ansi_date_re.search(value):
            raise ValueError("Enter a valid date in YYYY-MM-DD format.")

        year, month, day = map(int, value.split('-'))
        try:
            return datetime.date(year, month, day)
        except ValueError, e:
            raise ValueError("Invalid date: %s" % str(e))


class DateTimeField(Field):
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


class DecimalField(Field):
    def to_python(self, value):
        if value is None:
            return value
        try:
            return decimal.Decimal(value)
        except decimal.InvalidOperation:
            raise ValueError("This value must be a decimal number.")


class FloatField(Field):
    def to_python(self, value):
        if value is None:
            return value
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError("This value must be a float.")


class IntegerField(Field):
    def to_python(self, value):
        if value is None:
            return value
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError("This value must be an integer.")


class StringField(Field):
    def to_python(self, value):
        if isinstance(value, basestring):
            return value
        if value is None:
            return value
        raise ValueError("This field must be a string.")


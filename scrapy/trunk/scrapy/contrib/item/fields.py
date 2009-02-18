import re

class ItemFieldValueError(Exception):
    pass


class ItemField(object):
    def __init__(self, required=False):
        self.required = required

    def to_python(self, value):
        pass


class BooleanItemField(ItemField):
    def to_python(self, value):
        if value in (True, False): return value
        if value in ('t', 'True', '1'): return True
        if value in ('f', 'False', '0'): return False
        raise ItemFieldValueError("This value must be either True or False.")


ansi_date_re = re.compile(r'^\d{4}-\d{1,2}-\d{1,2}$')


class DateItemField(ItemField):
    def to_python(self, value):
        if value is None:
            return value
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value

        if not ansi_date_re.search(value):
            raise ItemFieldValueError(
                "Enter a valid date in YYYY-MM-DD format.")

        year, month, day = map(int, value.split('-'))
        try:
            return datetime.date(year, month, day)
        except ValueError, e:
            raise ItemFieldValueError("Invalid date: %s" % str(e))


class DecimalItemField(ItemField):
    def to_python(self, value):
        if value is None:
            return value
        try:
            return decimal.Decimal(value)
        except decimal.InvalidOperation:
            raise ItemFieldValueError("This value must be a decimal number.")


class FloatItemField(ItemField):
    def to_python(self, value):
        if value is None:
            return value
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ItemFieldValueError("This value must be a float.")


class IntegerItemField(ItemField):
    def to_python(self, value):
        if value is None:
            return value
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ItemFieldValueError("This value must be an integer.")


class StringItemField(ItemField):
    def to_python(self, value):
        if isinstance(value, basestring):
            return value
        if value is None:
            return value
        raise ItemFieldValueError("This field must be a string.")


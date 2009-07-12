import datetime
import decimal
import unittest

from scrapy.contrib_exp.newitem import Item, fields
from scrapy.contrib_exp.newitem.fields import BaseField


class NewItemTest(unittest.TestCase):

    def test_simple(self):
        class TestItem(Item):
            name = fields.StringField()

        i = TestItem()
        i.name = 'name'
        assert i.name == 'name'

    def test_init(self):
        class TestItem(Item):
            name = fields.StringField()
        
        i = TestItem()
        assert i.name is None

        i2 = TestItem({'name': 'john doe'})
        assert i2.name == 'john doe'

        self.assertRaises(TypeError, TestItem, name='john doe')

        self.assertRaises(AttributeError, TestItem, {'name': 'john doe', 'other': 'foo'})

    def test_multi(self):
        class TestMultiItem(Item):
            name = fields.StringField()
            names = fields.MultiValuedField(fields.StringField)

        i = TestMultiItem()
        i.name = 'name'
        i.names = ['name1', 'name2']
        assert i.names == ['name1', 'name2']

    def test_invalid_field(self):
        class TestItem(Item):
            pass

        i = TestItem()
        def set_invalid_field():
            i.field = 'text'

        self.assertRaises(AttributeError, set_invalid_field)

        def get_invalid_field():
            return i.field

        self.assertRaises(AttributeError, get_invalid_field)

    def test_default_value(self):
        class TestItem(Item):
            name = fields.StringField(default='John')
 
        i = TestItem()
        assert i.name == 'John'

    def test_to_python_iter(self):
        class TestItem(Item):
            name = fields.StringField()
 
        i = TestItem()
        i.name = ('John', 'Doe')
        assert i.name == 'John Doe'

    def test_repr(self):
        class TestItem(Item):
            name = fields.StringField()
            number = fields.IntegerField()

        i = TestItem()
        i.name = 'John Doe'
        i.number = '123'
        itemrepr = repr(i)
        assert itemrepr == "TestItem({'name': 'John Doe', 'number': 123})"

        i2 = eval(itemrepr)
        assert i2.name == 'John Doe'
        assert i2.number == 123


class NewItemFieldsTest(unittest.TestCase):
    
    def test_base_field(self):
        f = fields.BaseField()

        assert f.default == None
        assert f.to_python(1) == 1

    def test_boolean_field(self):
        class TestItem(Item):
            field = fields.BooleanField()

        i = TestItem()

        i.field = True
        assert i.field == True
    
        i.field = 1
        assert i.field == True

        i.field = False
        assert i.field == False

        i.field = 0
        assert i.field == False

    def test_date_field(self):
        class TestItem(Item):
            field = fields.DateField()

        i = TestItem()

        d_today = datetime.date.today()
        i.field = d_today
        assert i.field == d_today

        dt_today = datetime.datetime.today()
        i.field = dt_today
        assert i.field == dt_today.date()
 
        i.field = '2009-05-21'
        assert i.field == datetime.date(2009, 5, 21)

        def set_invalid_format():
            i.field = '21-05-2009'

        self.assertRaises(ValueError, set_invalid_format)

        def set_invalid_date():
            i.field = '2009-05-51'

        self.assertRaises(ValueError, set_invalid_date)

    def test_datetime_field(self):
        class TestItem(Item):
            field = fields.DateTimeField()

        i = TestItem()

        dt_today = datetime.datetime.today()
        i.field = dt_today
        assert i.field == dt_today

        d_today = datetime.date.today()
        i.field = d_today
        assert i.field == datetime.datetime(d_today.year, d_today.month,
                                            d_today.day)

        i.field = '2009-05-21 11:08:10.100'
        assert i.field == datetime.datetime(2009, 5, 21, 11, 8, 10, 100)
 
        i.field = '2009-05-21 11:08:10'
        assert i.field == datetime.datetime(2009, 5, 21, 11, 8, 10)

        i.field = '2009-05-21 11:08'
        assert i.field == datetime.datetime(2009, 5, 21, 11, 8)

        i.field = '2009-05-21'
        assert i.field == datetime.datetime(2009, 5, 21)

        def set_invalid_usecs():
            i.field = '2009-05-21 11:08:10.usecs'

        self.assertRaises(ValueError, set_invalid_usecs)

        def set_invalid_format():
            i.field = '21-05-2009'

        self.assertRaises(ValueError, set_invalid_format)

        def set_invalid_date():
            i.field = '2009-05-51'

        self.assertRaises(ValueError, set_invalid_date)

    def test_decimal_field(self):
        class TestItem(Item):
            field = fields.DecimalField()

        i = TestItem()

        i.field = decimal.Decimal('3.14')
        assert i.field == decimal.Decimal('3.14')

        i.field = '3.14'
        assert i.field == decimal.Decimal('3.14')
        
        def set_invalid_value():
            i.field = 'text'

        self.assertRaises(decimal.InvalidOperation, set_invalid_value)

    def test_float_field(self):
        class TestItem(Item):
            field = fields.FloatField()

        i = TestItem()

        i.field = 3.14
        assert i.field == 3.14

        i.field = '3.14'
        assert i.field == 3.14
        
        def set_invalid_value():
            i.field = 'text'

        self.assertRaises(ValueError, set_invalid_value)

    def test_integer_field(self):
        class TestItem(Item):
            field = fields.IntegerField()

        i = TestItem()

        i.field = 3
        assert i.field == 3

        i.field = '3'
        assert i.field == 3

        def set_invalid_value():
            i.field = 'text'

        self.assertRaises(ValueError, set_invalid_value)

    def test_string_field(self):
        class TestItem(Item):
            field = fields.StringField()

        i = TestItem()

        i.field = 'hello'
        assert i.field == 'hello'

        def set_invalid_value():
            i.field = 3 

        self.assertRaises(ValueError, set_invalid_value)


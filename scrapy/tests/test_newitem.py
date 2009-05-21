import datetime
import decimal
import unittest

from scrapy.contrib_exp.newitem import *


class NewItemTest(unittest.TestCase):

    def test_simple(self):
        class TestItem(Item):
            name = StringField()

        i = TestItem()
        i.name = 'name'
        assert i.name == 'name'

    def test_multi(self):
        class TestMultiItem(Item):
            name = StringField()
            names = MultiValuedField(StringField)

        i = TestMultiItem()
        i.name = 'name'
        i.names = ['name1', 'name2']
        assert i.names == ['name1', 'name2']


class NewItemFieldsTest(unittest.TestCase):
    def test_boolean_field(self):
        class TestItem(Item):
            field = BooleanField()

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
            field = DateField()

        i = TestItem()

        today = datetime.date.today()
        i.field = today
        assert i.field == today
 
        i.field = '2009-05-21'
        assert i.field == datetime.date(2009, 5, 21)

    def test_datetime_field(self):
        class TestItem(Item):
            field = DateTimeField()

        i = TestItem()

        dt_today = datetime.datetime.today()
        i.field = dt_today
        assert i.field == dt_today

        d_today = datetime.date.today()
        i.field = d_today
        assert i.field == datetime.datetime(d_today.year, d_today.month,
                                            d_today.day)
 
        i.field = '2009-05-21 11:08:10'
        assert i.field == datetime.datetime(2009, 5, 21, 11, 8, 10)

        i.field = '2009-05-21 11:08'
        assert i.field == datetime.datetime(2009, 5, 21, 11, 8)

        i.field = '2009-05-21'
        assert i.field == datetime.datetime(2009, 5, 21)

    def test_decimal_field(self):
        class TestItem(Item):
            field = DecimalField()

        i = TestItem()

        i.field = decimal.Decimal('3.14')
        assert i.field == decimal.Decimal('3.14')

        i.field = '3.14'
        assert i.field == decimal.Decimal('3.14')

    def test_float_field(self):
        class TestItem(Item):
            field = FloatField()

        i = TestItem()

        i.field = 3.14
        assert i.field == 3.14

        i.field = '3.14'
        assert i.field == 3.14

    def test_integer_field(self):
        class TestItem(Item):
            field = IntegerField()

        i = TestItem()

        i.field = 3
        assert i.field == 3

        i.field = '3'
        assert i.field == 3

    def test_sting_field(self):
        class TestItem(Item):
            field = StringField()

        i = TestItem()

        i.field = 'hello'
        assert i.field == 'hello'


import datetime
import decimal
import unittest

from scrapy.newitem import Item, fields
from scrapy.newitem.fields import BaseField


class NewItemTest(unittest.TestCase):

    def test_simple(self):
        class TestItem(Item):
            name = fields.TextField()

        i = TestItem()
        i['name'] = u'name'
        self.assertEqual(i['name'], u'name')

    def test_init(self):
        class TestItem(Item):
            name = fields.TextField()

        i = TestItem()
        self.assertRaises(KeyError, i.__getitem__, 'name')

        i2 = TestItem(name=u'john doe')
        self.assertEqual(i2['name'], u'john doe')

        i3 = TestItem({'name': u'john doe'})
        self.assertEqual(i3['name'], u'john doe')

        i4 = TestItem(i3)
        self.assertEqual(i4['name'], u'john doe')

        self.assertRaises(KeyError, TestItem, {'name': u'john doe',
                                               'other': u'foo'})

        self.assertRaises(TypeError, TestItem, name=set())

    def test_multi(self):
        class TestListItem(Item):
            name = fields.TextField()
            names = fields.ListField(fields.TextField)

        i = TestListItem()
        i['name'] = u'name'
        i['names'] = [u'name1', u'name2']
        self.assertEqual(i['names'], [u'name1', u'name2'])

    def test_invalid_field(self):
        class TestItem(Item):
            pass

        i = TestItem()
        self.assertRaises(KeyError, i.__setitem__, 'field', 'text')
        self.assertRaises(KeyError, i.__getitem__, 'field')

    def test_default_value(self):
        class TestItem(Item):
            name = fields.TextField(default=u'John')
 
        i = TestItem()
        self.assertEqual(i['name'], u'John')

    def test_wrong_default(self):
        self.assertRaises(TypeError, fields.TextField, default=set())

    def test_repr(self):
        class TestItem(Item):
            name = fields.TextField()
            number = fields.IntegerField()

        i = TestItem()
        i['name'] = u'John Doe'
        i['number'] = '123'
        itemrepr = repr(i)
        self.assertEqual(itemrepr,
                         "TestItem(name=u'John Doe', number=123)")

        i2 = eval(itemrepr)
        self.assertEqual(i2['name'], 'John Doe')
        self.assertEqual(i2['number'], 123)

    def test_private_attr(self):
        class TestItem(Item):
            name = fields.TextField()

        i = TestItem()
        i._private = 'test'
        self.assertEqual(i._private, 'test')

    def test_custom_methods(self):
        class TestItem(Item):
            name = fields.TextField()

            def get_name(self):
                return self['name']

            def change_name(self, name):
                self['name'] = name

        i = TestItem()
        self.assertRaises(KeyError, i.get_name)
        i['name'] = u'lala'
        self.assertEqual(i.get_name(), u'lala')
        i.change_name(u'other')
        self.assertEqual(i.get_name(), 'other')

    def test_metaclass(self):
        class TestItem(Item):
            name = fields.TextField()
            keys = fields.TextField() 
            values = fields.TextField() 

        i = TestItem()
        i['name'] = u'John'
        self.assertEqual(i.keys(), ['name'])
        self.assertEqual(i.values(), ['John'])

        i['keys'] = u'Keys'
        i['values'] = u'Values'
        self.assertEqual(i.keys(), ['keys', 'values', 'name'])
        self.assertEqual(i.values(), [u'Keys', u'Values', u'John'])

    def test_metaclass_inheritance(self):
        class BaseItem(Item):
            name = fields.TextField()
            keys = fields.TextField() 
            values = fields.TextField() 

        class TestItem(BaseItem):
            keys = fields.IntegerField()

        i = TestItem()
        i['keys'] = 3
        self.assertEqual(i.keys(), ['keys'])
        self.assertEqual(i.values(), [3])

    def test_to_dict(self):
        class TestItem(Item):
            name = fields.TextField()

        i = TestItem()
        i['name'] = u'John'
        self.assertEqual(dict(i), {'name': u'John'})

    def test_id(self):
        class TestItem(Item):
            name = fields.TextField()

        i = TestItem()
        self.assertRaises(NotImplementedError, i.get_id)

        class IdItem(Item):
            id = fields.IntegerField()

            def get_id(self):
                return self['id']

        i = IdItem()
        i['id'] = 11
        self.assertEqual(i.get_id(), 11)


class NewItemFieldsTest(unittest.TestCase):
    
    def test_base_field(self):
        f = fields.BaseField()

        self.assert_(f.get_default() is None)
        self.assertRaises(NotImplementedError, f.to_python, 1)

    def test_boolean_field(self):
        class TestItem(Item):
            field = fields.BooleanField()

        i = TestItem()

        i['field'] = True
        self.assert_(i['field'] is True)
    
        i['field'] = 1
        self.assert_(i['field'] is True)

        i['field'] = False
        self.assert_(i['field'] is False)

        i['field'] = 0
        self.assert_(i['field'] is False)

        i['field'] = None
        self.assert_(i['field'] is False)

    def test_date_field(self):
        class TestItem(Item):
            field = fields.DateField()

        i = TestItem()

        d_today = datetime.date.today()
        i['field'] = d_today
        self.assertEqual(i['field'], d_today)

        dt_today = datetime.datetime.today()
        i['field'] = dt_today
        self.assertEqual(i['field'], dt_today.date())
 
        i['field'] = '2009-05-21'
        self.assertEqual(i['field'], datetime.date(2009, 5, 21))

        self.assertRaises(ValueError, i.__setitem__, 'field', '21-05-2009')

        self.assertRaises(ValueError, i.__setitem__, 'field', '2009-05-51')

        self.assertRaises(TypeError, i.__setitem__, 'field', None)

    def test_datetime_field(self):
        class TestItem(Item):
            field = fields.DateTimeField()

        i = TestItem()

        dt_today = datetime.datetime.today()
        i['field'] = dt_today
        self.assertEqual(i['field'], dt_today)

        d_today = datetime.date.today()
        i['field'] = d_today
        self.assertEqual(i['field'], datetime.datetime(d_today.year,
                                                    d_today.month, d_today.day))

        i['field'] = '2009-05-21 11:08:10.100'
        self.assertEqual(i['field'], datetime.datetime(2009, 5, 21, 11, 8, 10,
                                                    100))
 
        i['field'] = '2009-05-21 11:08:10'
        self.assertEqual(i['field'], datetime.datetime(2009, 5, 21, 11, 8, 10))

        i['field'] = '2009-05-21 11:08'
        self.assertEqual(i['field'], datetime.datetime(2009, 5, 21, 11, 8))

        i['field'] = '2009-05-21'
        self.assertEqual(i['field'], datetime.datetime(2009, 5, 21))

        self.assertRaises(ValueError, i.__setitem__, 'field', '2009-05-21 11:08:10.usecs')

        self.assertRaises(ValueError, i.__setitem__, 'field', '21-05-2009')

        self.assertRaises(ValueError, i.__setitem__, 'field', '2009-05-51')

        self.assertRaises(TypeError, i.__setitem__, 'field', None)

    def test_decimal_field(self):
        class TestItem(Item):
            field = fields.DecimalField()

        i = TestItem()

        i['field'] = decimal.Decimal('3.14')
        self.assertEqual(i['field'], decimal.Decimal('3.14'))

        i['field'] = '3.14'
        self.assertEqual(i['field'], decimal.Decimal('3.14'))
        
        self.assertRaises(decimal.InvalidOperation, i.__setitem__, 'field', 'text')

        self.assertRaises(TypeError, i.__setitem__, 'field', None)

    def test_float_field(self):
        class TestItem(Item):
            field = fields.FloatField()

        i = TestItem()

        i['field'] = 3.14
        self.assertEqual(i['field'], 3.14)

        i['field'] = '3.14'
        self.assertEqual(i['field'], 3.14)
        
        self.assertRaises(ValueError, i.__setitem__, 'field', 'text')

        self.assertRaises(TypeError, i.__setitem__, 'field', None)

    def test_integer_field(self):
        class TestItem(Item):
            field = fields.IntegerField()

        i = TestItem()

        i['field'] = 3
        self.assertEqual(i['field'], 3)

        i['field'] = '3'
        self.assertEqual(i['field'], 3)

        self.assertRaises(ValueError, i.__setitem__, 'field', 'text')

        self.assertRaises(TypeError, i.__setitem__, 'field', None)

    def test_text_field(self):
        class TestItem(Item):
            field = fields.TextField()

        i = TestItem()

        # valid castings
        i['field'] = u'hello'
        self.assertEqual(i['field'], u'hello')
        self.assert_(isinstance(i['field'], unicode))

        i['field'] = 3
        self.assertEqual(i['field'], u'3')
        self.assert_(isinstance(i['field'], unicode))

        i['field'] = 3.2
        self.assertEqual(i['field'], u'3.2')
        self.assert_(isinstance(i['field'], unicode))

        i['field'] = 100L
        self.assertEqual(i['field'], u'100')
        self.assert_(isinstance(i['field'], unicode))

        # invalid castings
        self.assertRaises(TypeError, i.__setitem__, 'field', [u'hello', u'world'])
        self.assertRaises(TypeError, i.__setitem__, 'field', 'string') # must be unicode!
        self.assertRaises(TypeError, i.__setitem__, 'field', set())
        self.assertRaises(TypeError, i.__setitem__, 'field', True)
        self.assertRaises(TypeError, i.__setitem__, 'field', None)


    def test_from_unicode_list(self):
        field = fields.BaseField()
        self.assertEqual(field.from_unicode_list([]), None)

        field = fields.TextField()
        self.assertEqual(field.from_unicode_list([]), u'')
        self.assertEqual(field.from_unicode_list([u'hello', u'world']), u'hello world')

        field = fields.ListField(fields.TextField)
        self.assertEqual(field.from_unicode_list([]), [])
        self.assertEqual(field.from_unicode_list([u'hello', u'world']), [u'hello', u'world'])

        field = fields.IntegerField()
        self.assertEqual(field.from_unicode_list([u'123']), 123)

    def test_time_field(self):
        class TestItem(Item):
            field = fields.TimeField()

        i = TestItem()

        dt_t = datetime.time(11, 8, 10, 100)
        i['field'] = dt_t
        self.assertEqual(i['field'], dt_t)

        self.assertRaises(TypeError, i.__setitem__, 'field', None)

        dt_dt = datetime.datetime.today()
        i['field'] = dt_dt
        self.assertEqual(i['field'], dt_dt.time)

        i['field'] = '11:08:10.100'
        self.assertEqual(i['field'], datetime.time(11, 8, 10, 100))
 
        i['field'] = '11:08:10'
        self.assertEqual(i['field'], datetime.time(11, 8, 10))

        i['field'] = '11:08'
        self.assertEqual(i['field'], datetime.time(11, 8))

        self.assertRaises(ValueError, i.__setitem__, 'field', '11:08:10.usecs')

        self.assertRaises(ValueError, i.__setitem__, 'field', '25:08:10')

        self.assertRaises(ValueError, i.__setitem__, 'field', 'string')


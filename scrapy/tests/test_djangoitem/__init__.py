import os
from twisted.trial import unittest

from scrapy.contrib.djangoitem import DjangoItem, Field

os.environ['DJANGO_SETTINGS_MODULE'] = 'scrapy.tests.test_djangoitem.settings'

try:
    import django
except ImportError:
    django = None

if django:
    from .models import Person, IdentifiedPerson
else:
    Person = None
    IdentifiedPerson = None


class BasePersonItem(DjangoItem):
    django_model = Person


class NewFieldPersonItem(BasePersonItem):
    other = Field()


class OverrideFieldPersonItem(BasePersonItem):
    age = Field()


class IdentifiedPersonItem(DjangoItem):
    django_model = IdentifiedPerson


class DjangoItemTest(unittest.TestCase):

    def setUp(self):
        if not django:
            raise unittest.SkipTest("Django is not available")

    def test_base(self):
        i = BasePersonItem()
        self.assertEqual(i.fields.keys(), ['age', 'name'])

    def test_new_fields(self):
        i = NewFieldPersonItem()
        self.assertEqual(i.fields.keys(), ['age', 'other', 'name'])

    def test_override_field(self):
        i = OverrideFieldPersonItem()
        self.assertEqual(i.fields.keys(), ['age', 'name'])

    def test_custom_primary_key_field(self):
        """
        Test that if a custom primary key exists, it is
        in the field list.
        """
        i = IdentifiedPersonItem()
        self.assertEqual(i.fields.keys(), ['age', 'identifier', 'name'])

    def test_save(self):
        i = BasePersonItem()
        self.assertEqual(i.fields.keys(), ['age', 'name'])

        i['name'] = 'John'
        i['age'] = '22'
        person = i.save(commit=False)

        self.assertEqual(person.name, 'John')
        self.assertEqual(person.age, '22')

    def test_override_save(self):
        i = OverrideFieldPersonItem()

        i['name'] = 'John'
        # it is not obvious that "age" should be saved also, since it was
        # redefined in child class
        i['age'] = '22'
        person = i.save(commit=False)

        self.assertEqual(person.name, 'John')
        self.assertEqual(person.age, '22')

    def test_validation(self):
        long_name = 'z' * 300
        i = BasePersonItem(name=long_name)
        self.assertFalse(i.is_valid())
        self.assertDictEqual(
            {
                'age': [u'This field cannot be null.'],
                'name': [u'Ensure this value has at most 255 characters (it has 300).']
            },
            i.errors)

        i = BasePersonItem(name='John')
        self.assertTrue(i.is_valid(exclude=['age']))
        self.assertDictEqual({}, i.errors)

        # once the item is validated, it does not validate again
        i['name'] = long_name
        self.assertTrue(i.is_valid())

    def test_override_validation(self):
        i = OverrideFieldPersonItem()
        i['name'] = 'John'
        self.assertFalse(i.is_valid())

        i = i = OverrideFieldPersonItem()
        i['name'] = 'John'
        i['age'] = '22'
        self.assertTrue(i.is_valid())


    def test_default_field_values(self):
        i = BasePersonItem()
        person = i.save(commit=False)
        self.assertEqual(person.name, 'Robot')

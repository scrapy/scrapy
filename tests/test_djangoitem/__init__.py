import os
from twisted.trial import unittest

from scrapy.contrib.djangoitem import DjangoItem, Field
from scrapy import optional_features

os.environ['DJANGO_SETTINGS_MODULE'] = 'tests.test_djangoitem.settings'

if 'django' in optional_features:
    from .models import Person, IdentifiedPerson

    class BasePersonItem(DjangoItem):
        django_model = Person

    class NewFieldPersonItem(BasePersonItem):
        other = Field()

    class OverrideFieldPersonItem(BasePersonItem):
        age = Field()

    class IdentifiedPersonItem(DjangoItem):
        django_model = IdentifiedPerson


class DjangoItemTest(unittest.TestCase):

    def assertSortedEqual(self, first, second, msg=None):
        return self.assertEqual(sorted(first), sorted(second), msg)

    def setUp(self):
        if 'django' not in optional_features:
            raise unittest.SkipTest("Django is not available")

    def test_base(self):
        i = BasePersonItem()
        self.assertSortedEqual(i.fields.keys(), ['age', 'name'])

    def test_new_fields(self):
        i = NewFieldPersonItem()
        self.assertSortedEqual(i.fields.keys(), ['age', 'other', 'name'])

    def test_override_field(self):
        i = OverrideFieldPersonItem()
        self.assertSortedEqual(i.fields.keys(), ['age', 'name'])

    def test_custom_primary_key_field(self):
        """
        Test that if a custom primary key exists, it is
        in the field list.
        """
        i = IdentifiedPersonItem()
        self.assertSortedEqual(i.fields.keys(), ['age', 'identifier', 'name'])

    def test_save(self):
        i = BasePersonItem()
        self.assertSortedEqual(i.fields.keys(), ['age', 'name'])

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
        self.assertEqual(set(i.errors), set(['age', 'name']))
        i = BasePersonItem(name='John')
        self.assertTrue(i.is_valid(exclude=['age']))
        self.assertEqual({}, i.errors)

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

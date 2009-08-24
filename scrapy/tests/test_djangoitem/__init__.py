import os
from twisted.trial import unittest

from scrapy.contrib_exp.djangoitem import DjangoItem, Field

os.environ['DJANGO_SETTINGS_MODULE'] = 'scrapy.tests.test_djangoitem.settings'

try:
    from models import Person
    django = True
except ImportError:
    django = False


class BasePersonItem(DjangoItem):
    django_model = Person


class NewFieldPersonItem(BasePersonItem):
    other = Field()


class OverrideFieldPersonItem(BasePersonItem):
    age = Field(default=1)


class DjangoItemTest(TestCase):
    
    def setUp(
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
        self.assertEqual(i.fields['age'], {'default': 1})

    def test_save(self):
        i = BasePersonItem()
        self.assertEqual(i.fields.keys(), ['age', 'name'])

        i['name'] = 'John'
        i['age'] = '22'
        person = i.save(commit=False)

        self.assertEqual(person.name, 'John')
        self.assertEqual(person.age, '22')


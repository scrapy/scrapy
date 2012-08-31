.. _topics-djangoitem:

==========
DjangoItem
==========

:class:`DjangoItem` is a class of item that gets its fields definition from a
Django model, you simply create a :class:`DjangoItem` and specify what Django
model it relates to.

Besides of getting the model fields defined on your item, :class:`DjangoItem`
provides a method to create and populate a Django model instance with the item
data.

Using DjangoItem
================

:class:`DjangoItem` works much like ModelForms in Django, you create a subclass
and define its ``django_model`` atribute to ve a valid Django model. With this
you will get an item with a field for each Django model field.

In addition, you can define fields that aren't present in the model and even
override fields that are present in the model defining them in the item. 

Let's see some examples:

Django model for the examples::

   class Person(models.Model):
       name = models.CharField(max_length=255)
       age = models.IntegerField()

Defining a basic :class:`DjangoItem`::
    
   class PersonItem(DjangoItem):
       django_model = Person
       
:class:`DjangoItem` work just like :class:`~scrapy.item.Item`::

   p = PersonItem()
   p['name'] = 'John'
   p['age'] = '22'

To obtain the Django model from the item, we call the extra method
:meth:`~DjangoItem.save` of the :class:`DjangoItem`::

   >>> person = p.save()
   >>> person.name
   'John'
   >>> person.age
   '22'
   >>> person.id
   1

As you see the model is already saved when we call :meth:`~DjangoItem.save`, we
can prevent this by calling it with ``commit=False``. We can use
``commit=False`` in :meth:`~DjangoItem.save` method to obtain an unsaved model::

   >>> person = p.save(commit=False)
   >>> person.name
   'John'
   >>> person.age
   '22'
   >>> person.id
   None

As said before, we can add other fields to the item::

   class PersonItem(DjangoItem):
       django_model = Person
       sex = Field()

   p = PersonItem()
   p['name'] = 'John'
   p['age'] = '22'
   p['sex'] = 'M'

.. note:: fields added to the item won't be taken into account when doing a :meth:`~DjangoItem.save`

And we can override the fields of the model with your own::

   class PersonItem(DjangoItem):
       django_model = Person
       name = Field(default='No Name')

This is usefull to provide properties to the field, like a default or any other
property that your project uses.

DjangoItem caveats
==================

DjangoItem is a rather convenient way to integrate Scrapy projects with Django
models, but bear in mind that Django ORM may not scale well if you scrape a lot
of items (ie. millions) with Scrapy. This is because a relational backend is
often not a good choice for a write intensive application (such as a web
crawler), specially if the database is highly normalized and with many indices.

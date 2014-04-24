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
and define its ``django_model`` attribute to be a valid Django model. With this
you will get an item with a field for each Django model field.

In addition, you can define fields that aren't present in the model and even
override fields that are present in the model defining them in the item.

Let's see some examples:

Creating a Django model for the examples::

    from django.db import models

    class Person(models.Model):
        name = models.CharField(max_length=255)
        age = models.IntegerField()

Defining a basic :class:`DjangoItem`::

    from scrapy.contrib.djangoitem import DjangoItem

    class PersonItem(DjangoItem):
        django_model = Person

:class:`DjangoItem` work just like :class:`~scrapy.item.Item`::

    >>> p = PersonItem()
    >>> p['name'] = 'John'
    >>> p['age'] = '22'

To obtain the Django model from the item, we call the extra method
:meth:`~DjangoItem.save` of the :class:`DjangoItem`::

    >>> person = p.save()
    >>> person.name
    'John'
    >>> person.age
    '22'
    >>> person.id
    1

The model is already saved when we call :meth:`~DjangoItem.save`, we
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

    import scrapy
    from scrapy.contrib.djangoitem import DjangoItem

    class PersonItem(DjangoItem):
        django_model = Person
        sex = scrapy.Field()

::

   >>> p = PersonItem()
   >>> p['name'] = 'John'
   >>> p['age'] = '22'
   >>> p['sex'] = 'M'

.. note:: fields added to the item won't be taken into account when doing a :meth:`~DjangoItem.save`

And we can override the fields of the model with your own::

    class PersonItem(DjangoItem):
        django_model = Person
        name = scrapy.Field(default='No Name')

This is useful to provide properties to the field, like a default or any other
property that your project uses.

DjangoItem caveats
==================

DjangoItem is a rather convenient way to integrate Scrapy projects with Django
models, but bear in mind that Django ORM may not scale well if you scrape a lot
of items (ie. millions) with Scrapy. This is because a relational backend is
often not a good choice for a write intensive application (such as a web
crawler), specially if the database is highly normalized and with many indices.

Django settings set up
======================

To use the Django models outside the Django application you need to set up the
``DJANGO_SETTINGS_MODULE`` environment variable and --in most cases-- modify
the ``PYTHONPATH`` environment variable to be able to import the settings
module.

There are many ways to do this depending on your use case and preferences.
Below is detailed one of the simplest ways to do it.

Suppose your Django project is named ``mysite``, is located in the path
``/home/projects/mysite`` and you have created an app ``myapp`` with the model
``Person``. That means your directory structure is something like this::

    /home/projects/mysite
    ├── manage.py
    ├── myapp
    │   ├── __init__.py
    │   ├── models.py
    │   ├── tests.py
    │   └── views.py
    └── mysite
        ├── __init__.py
        ├── settings.py
        ├── urls.py
        └── wsgi.py

Then you need to add ``/home/projects/mysite`` to the ``PYTHONPATH``
environment variable and set up the environment variable
``DJANGO_SETTINGS_MODULE`` to ``mysite.settings``. That can be done in your
Scrapy's settings file by adding the lines below::

  import sys
  sys.path.append('/home/projects/mysite')

  import os
  os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings'

Notice that we modify the ``sys.path`` variable instead the ``PYTHONPATH``
environment variable as we are already within the python runtime. If everything
is right, you should be able to start the ``scrapy shell`` command and import
the model ``Person`` (i.e. ``from myapp.models import Person``).

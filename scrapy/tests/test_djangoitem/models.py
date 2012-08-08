from django.db import models


class Person(models.Model):
    name = models.CharField(max_length=255, default='Robot')
    age = models.IntegerField()

    class Meta:
        app_label = 'test_djangoitem'

class IdentifiedPerson(models.Model):
    identifier = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=255)
    age = models.IntegerField()

    class Meta:
        app_label = 'test_djangoitem'

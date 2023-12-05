from django.db import models


class OtherModel(models.Model):
    pass


class SampleModel(models.Model):
    value = models.IntegerField()
    not_editable = models.IntegerField(editable=False)
    created = models.DateTimeField(auto_now_add=True)

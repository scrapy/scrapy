from datetime import datetime

from django.db import models
from django.template.defaultfilters import slugify
from django.utils.translation import ugettext_lazy as _


class Group(models.Model):
    name = models.CharField(_("name"), max_length=64, core=True, blank=False)
    slug = models.SlugField(_("slug"), editable=False, unique=True,
                            prepopulate_from=("name",))

    # automatic dates
    created = models.DateTimeField(_("created"), core=True, editable=False)
    updated = models.DateTimeField(_("updated"), core=True, editable=False)

    def save(self):
        if not self.id:
            self.created = datetime.now()
        self.updated = datetime.now()
        self.slug = slugify(self.name)
        super(Group, self).save()

    def __unicode__(self):
        return self.name

    class Meta:
        verbose_name = _("group")
        verbose_name_plural = _("groups")

    class Admin:
        list_display = ("name", "slug",)


class Link(models.Model):
    text = models.CharField(_("text"), max_length=1024, core=True, blank=False)
    address = models.CharField(_("address"), max_length=1024, core=True,
                               blank=False)
    group = models.ManyToManyField(Group, verbose_name=_("group"), blank=True,
                                   null=False)

    # automatic dates
    created = models.DateTimeField(core=True, editable=False)
    updated = models.DateTimeField(core=True, editable=False)

    def save(self):
        if not self.id:
            self.created = datetime.now()
        self.updated = datetime.now()
        super(Link, self).save()

    def __unicode__(self):
        return self.address

    class Meta:
        verbose_name = _("link")
        verbose_name_plural = _("links")

    class Admin:
        list_display = ("text", "address",)
        list_filter = ("group", )

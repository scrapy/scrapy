from datetime import datetime

from django.db import models
from django.template.defaultfilters import slugify
from django.utils.translation import ugettext_lazy as _


REST_HELP_TEXT = _("""ReST markup language allowed
                      <a href='http://en.wikipedia.org/wiki/ReStructuredText'>
                      Read more</a>""")

MAIN_HELP_TEXT = _("Useful to filter articles, like those public on homepage")


class Article(models.Model):
    title = models.CharField(_("title"), max_length=256, core=True,
                             blank=False)
    slug = models.SlugField(_("slug"), prepopulate_from=("title",),
                            editable=False)
    text = models.TextField(_("text"), core=True, help_text=REST_HELP_TEXT)
    main = models.BooleanField(_("main"), core=True, blank=False,
                               default=False, help_text=MAIN_HELP_TEXT)
    order = models.IntegerField(_("order"), core=True, blank=False, default=0)


    # automatic dates
    created = models.DateTimeField(core=True, editable=False)
    updated = models.DateTimeField(core=True, editable=False)


    def order_up(self):
        self.order += 1
        self.save()

    def order_down(self):
        self.order -= 1
        self.save()

    def save(self):
        if not self.id:
            self.created = datetime.now()
        self.updated = datetime.now()
        self.slug = slugify(self.title)
        super(Article, self).save()

    def __unicode__(self):
        return self.title
    
    # ugly, but django-admin isn't very versatile right now
    def order_link(self):
        return _("%(order)s (<a href='/article/%(id)s/order/up/'>Up</a>" \
               " | <a href='/article/%(id)s/order/down/'>Down</a>)") % \
               { "order": self.order, "id": self.id }
    order_link.short_description = u"order"
    order_link.allow_tags = True
    
    class Admin:
        list_display = ("title", "main", "order_link", "updated")
        list_filter = ("main", "created")

    class Meta:
        verbose_name = _("article")
        verbose_name_plural = _("articles")
        ordering = [ "-order", ]

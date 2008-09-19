from datetime import datetime

from django.db import models
from django.utils.translation import ugettext_lazy as _


class DownloadLink(models.Model):
    description = models.CharField(_("description"), max_length=512,
                                   blank=True, default='')
    address = models.CharField(_("address"), max_length=1024, blank=False)
    text = models.CharField(_("link text"), max_length=512, blank=False,
                            default=_("download"))
    public = models.BooleanField(_("public"), blank=False, default=True)

    # automatic dates
    created = models.DateTimeField(_("created"), editable=False)
    updated = models.DateTimeField(_("updated"), editable=False)

    def toggle_public(self):
        self.public = not self.public
        self.save()

    def save(self):
        if not self.id:
            self.created = datetime.now()
        self.updated = datetime.now()
        super(DownloadLink, self).save()

    def __unicode__(self):
        return self.address

    # ugly, but django-admin isn't very versatile right now
    def public_link(self):
        img_url = "/media/img/admin/icon-%s.gif" % \
                  (self.public and "yes" or "no")
        html = _('<img alt="%s" src="' + img_url + '"/> ' \
                 '(<a href="%s/toggle/">Toggle</a>)')
        return html % (_(str(self.public)), self.id)

    public_link.short_description = u"public"
    public_link.allow_tags = True

#     class Admin:
#         list_display = ("text", "address", "public_link", "created")
#         list_filter = ("public", "created")
#         save_on_top = True

    class Meta:
        verbose_name = _("download link")
        verbose_name_plural = _("download links")
        ordering = ["-created",]

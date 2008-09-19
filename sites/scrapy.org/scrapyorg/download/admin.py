from django.contrib import admin

from scrapyorg.download.models import DownloadLink


class DownloadLinkAdmin(admin.ModelAdmin):
    list_display = ("text", "address", "public_link", "created")
    list_filter = ("public", "created")
    search_fields = ("address", "text")

admin.site.register(DownloadLink, DownloadLinkAdmin)

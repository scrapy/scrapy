from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect

from scrapyorg.download.models import DownloadLink


def toggle_public(request, link_id):
    link = get_object_or_404(DownloadLink, pk=link_id)
    link.toggle_public()
    return HttpResponseRedirect("/admin/download/downloadlink/")

from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib.admin.views.decorators import staff_member_required

from scrapyorg.download.models import DownloadLink


@staff_member_required
def toggle_public(request, link_id):
    link = get_object_or_404(DownloadLink, pk=link_id)
    link.toggle_public()
    return HttpResponseRedirect("/admin/download/downloadlink/")

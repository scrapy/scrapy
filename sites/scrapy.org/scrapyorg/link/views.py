from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect

from scrapyorg.link.models import GroupLink


def position_up(request, grouplink_id):
    grouplink = get_object_or_404(GroupLink, pk=grouplink_id)
    grouplink.position_up()
    return HttpResponseRedirect("/admin/link/grouplink/")


def position_down(request, grouplink_id):
    grouplink = get_object_or_404(GroupLink, pk=grouplink_id)
    grouplink.position_down()
    return HttpResponseRedirect("/admin/link/grouplink/")

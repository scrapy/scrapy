from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib.admin.views.decorators import staff_member_required

from scrapyorg.article.models import Article


@staff_member_required
def position_up(request, article_id):
    article = get_object_or_404(Article, pk=article_id)
    article.position_up()
    return HttpResponseRedirect("/admin/article/article/")

@staff_member_required
def position_down(request, article_id):
    article = get_object_or_404(Article, pk=article_id)
    article.position_down()
    return HttpResponseRedirect("/admin/article/article/")

@staff_member_required
def publish_toggle(request, article_id):
    article = get_object_or_404(Article, pk=article_id)
    article.toggle_publish()
    return HttpResponseRedirect("/admin/article/article/")

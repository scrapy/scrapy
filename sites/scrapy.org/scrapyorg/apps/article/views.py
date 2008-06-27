from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect

from article.models import Article


def position_up(request, article_id):
    article = get_object_or_404(Article, pk=article_id)
    article.position_up()
    return HttpResponseRedirect("/admin/article/article/")


def position_down(request, article_id):
    article = get_object_or_404(Article, pk=article_id)
    article.position_down()
    return HttpResponseRedirect("/admin/article/article/")

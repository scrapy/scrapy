from django.conf.urls.defaults import *

from article.views import *


urlpatterns = patterns('',
    (r"^(?P<article_id>\d+)/position/up/$", position_up),
    (r"^(?P<article_id>\d+)/position/down/$", position_down),
)

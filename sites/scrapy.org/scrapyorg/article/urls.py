from django.conf.urls.defaults import *

from scrapyorg.article.views import *


urlpatterns = patterns('',
    (r"^$", render_template, { "path": "home" }),
    (r"(?P<path>.*)/", render_template),
)

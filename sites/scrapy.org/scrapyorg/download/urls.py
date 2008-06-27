from django.conf.urls.defaults import *

from scrapyorg.download.views import *


urlpatterns = patterns('',
    (r"^(?P<link_id>\d+)/public/toggle/$", toggle_public),
)

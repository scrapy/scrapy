from django.conf.urls.defaults import *

from download.views import *


urlpatterns = patterns('',
    (r"^(?P<link_id>\d+)/public/toggle/$", toggle_public),
)

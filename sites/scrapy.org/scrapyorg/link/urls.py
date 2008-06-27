from django.conf.urls.defaults import *

from link.views import *


urlpatterns = patterns('',
    (r"^(?P<grouplink_id>\d+)/position/up/$", position_up),
    (r"^(?P<grouplink_id>\d+)/position/down/$", position_down),
)

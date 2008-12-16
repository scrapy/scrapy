from django.conf import settings
from django.conf.urls.defaults import *

from scrapyorg.docs.views import document
from scrapyorg.docs.views import images


urlpatterns = patterns('',
    url(r'^$', document, {'url': ''}),
    url(r'^(?P<url>[\w./-]*)/$', document),
    url(r'^_images/(?P<path>.*)$', images),
)

if settings.DEBUG: # devel
    urlpatterns += patterns('',         
        (r'^%s/(?P<path>.*)$' % settings.MEDIA_URL[1:],
          'django.views.static.serve',
          {'document_root': settings.MEDIA_ROOT}),
    )


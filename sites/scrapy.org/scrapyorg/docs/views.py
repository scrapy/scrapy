import cPickle as pickle
import os

import django.views.static
from django.conf import settings
from django.http import Http404
from django.shortcuts import render_to_response
from django.template import RequestContext


def document(request, url):
    docroot = settings.DOC_PICKLE_ROOT

    if os.path.exists(os.path.join(docroot, url, 'index.fpickle')):
        docpath = os.path.join(docroot, url, 'index.fpickle')
    elif os.path.exists(os.path.join(docroot, url + '.fpickle')):
        docpath = os.path.join(docroot, url + '.fpickle')
    else:
        raise Http404("'%s' does not exist" % url)

    docfile = open(docpath, 'rb')
    doc = pickle.load(docfile)

    return render_to_response('docs/doc.html', {'doc': doc},
                              context_instance=RequestContext(request))


def images(request, path):
    return django.views.static.serve(
	    request,
        document_root = os.path.join(settings.DOC_PICKLE_ROOT, '_images'),
        path = path,
    )

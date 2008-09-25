from __future__ import with_statement

import re
import os
import time
import sha
import urllib
import urlparse
from cStringIO import StringIO

import Image

from scrapy import log
from scrapy.stats import stats
from scrapy.http import Request
from scrapy.core.exceptions import DropItem, NotConfigured
from scrapy.core.exceptions import HttpException
from scrapy.conf import settings

from scrapy.contrib.pipeline.media import MediaPipeline

# the age at which we download images again
IMAGE_EXPIRES = settings.getint('IMAGES_EXPIRES', 90)

class NoimagesDrop(DropItem):
    pass

class ImageException(Exception):
    """General image error exception"""


class ImagesPipeline(MediaPipeline):
    MEDIA_TYPE = 'image'
    THUMBS = None
#     THUMBS = (
#             ("50", (50, 50)),
#             ("110", (110, 110)),
#             ("270", (270, 270))
#     )
    MIN_WIDTH = 0
    MIN_HEIGHT = 0

    def __init__(self):
        if not settings['IMAGES_DIR']:
            raise NotConfigured

        self.BASEDIRNAME = settings['IMAGES_DIR']
        self.mkdir(self.BASEDIRNAME)

        self.MIN_WIDTH = settings.getint('IMAGES_MIN_WIDTH', 0)
        self.MIN_HEIGHT = settings.getint('IMAGES_MIN_HEIGHT', 0)
        MediaPipeline.__init__(self)

    def media_to_download(self, request, info):
        relative, absolute = self._get_paths(request)
        if not should_download(absolute):
            self.inc_stats(info.domain, 'uptodate')
            referer = request.headers.get('Referer')
            log.msg('Image (uptodate): Downloaded %s from %s referred in <%s>' % \
                    (self.MEDIA_TYPE, request, referer), level=log.DEBUG, domain=info.domain)
            return relative

    def media_downloaded(self, response, request, info):
        mtype = self.MEDIA_TYPE
        referer = request.headers.get('Referer')

        if not response or not response.body.to_string():
            msg = 'Image (empty): Empty %s (no content) in %s referred in <%s>: Empty image (no-content)' % (mtype, request, referer)
            log.msg(msg, level=log.WARNING, domain=info.domain)
            raise ImageException(msg)

        result = self.save_image(response, request, info) # save and thumbs response

        status = 'cached' if getattr(response, 'cached', False) else 'downloaded'
        msg = 'Image (%s): Downloaded %s from %s referred in <%s>' % (status, mtype, request, referer)
        log.msg(msg, level=log.DEBUG, domain=info.domain)
        self.inc_stats(info.domain, status)
        return result

    def media_failed(self, failure, request, info):
        referer = request.headers.get('Referer')
        errmsg = str(failure.value) if isinstance(failure.value, HttpException) else str(failure)
        msg = 'Image (http-error): Error downloading %s from %s referred in <%s>: %s' % (self.MEDIA_TYPE, request, referer, errmsg)
        log.msg(msg, level=log.WARNING, domain=info.domain)
        raise ImageException(msg)

    def save_image(self, response, request, info):
        mtype = self.MEDIA_TYPE
        relpath, abspath = self._get_paths(request)
        dirname = os.path.dirname(abspath)
        self.mkdir(dirname, info)

        try:
            save_image_with_thumbnails(response, abspath, self.THUMBS, self.MIN_WIDTH, self.MIN_HEIGHT)
        except ImageException, ex:
            log.msg(str(ex), level=log.WARNING, domain=info.domain)
            raise ex
        except Exception, ex:
            msg = 'Image (processing-error): Error thumbnailing %s from %s referred in <%s>: %s' % (mtype, request, referer, ex)
            log.msg(msg, level=log.WARNING, domain=info.domain)
            raise ImageException(msg)

        return relpath # success value sent as input result for item_media_downloaded

    def _get_paths(self, request):
        relative = image_path(request.url)
        absolute = os.path.join(self.BASEDIRNAME, relative)
        return relative, absolute

    def mkdir(self, dirname, info=None):
        already_created = info.extra.setdefault('created_directories', set()) if info else set()
        if dirname not in already_created:
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            already_created.add(dirname)

    def inc_stats(self, domain, status):
        stats.incpath('%s/image_count' % domain)
        stats.incpath('%s/image_status_count/%s' % (domain, status))



def should_download(path):
    """Should the image downloader download the image to the location specified
    """
    try:
        mtime = os.path.getmtime(path)
        age_seconds = time.time() - mtime
        age_days = age_seconds / 60 / 60 / 24
        return age_days > IMAGE_EXPIRES
    except:
        return True

_MULTIPLE_SLASHES_REGEXP = re.compile(r"\/{2,}")
_FINAL_SLASH_REGEXP = re.compile(r"\/$")
def image_path(url):
    """Return the relative path on the target filesystem for an image to be
    downloaded to.
    """
    _, netloc, urlpath, query, _ = urlparse.urlsplit(url)
    urlpath = _MULTIPLE_SLASHES_REGEXP.sub('/', urlpath)
    urlpath = _FINAL_SLASH_REGEXP.sub('.jpg', urlpath)
    if os.sep != '/':
        urlpath.replace('/', os.sep)
    if query:
        img_path = os.path.join(netloc, sha.sha(url).hexdigest())
    else:
        img_path = os.path.join(netloc, urlpath[1:])
    return urllib.unquote(img_path)


def thumbnail_name(image, sizestr):
    """Get the name of a thumbnail image given the name of the original file.

    There will can be many types of thumbnails, so we will have a "name" for
    each type.
    """
    return os.path.splitext(image)[0] + '_' + sizestr + '.jpg'

def save_scaled_image(image, img_path, name, size):
    thumb = image.copy() if image.mode == 'RGB' else image.convert('RGB')
    thumb.thumbnail(size, Image.ANTIALIAS)
    filename = thumbnail_name(img_path, name)
    thumb.save(filename, 'JPEG')

def save_image_with_thumbnails(response, path, thumbsizes, min_width=0, min_height=0):
    memoryfile = StringIO(response.body.to_string())
    im = Image.open(memoryfile)
    if im.mode != 'RGB':
        log.msg("Found non-RGB image during scraping %s" % path, level=log.WARNING)
    for name, size in thumbsizes or []:
        save_scaled_image(im, path, name, size)
    try:
        im.save(path)
    except Exception, ex:
        log.msg("Image (processing-error): cannot process %s, so writing direct file: Error: %s" % (path, ex))
        f = open(path, 'wb')
        f.write(response.body.to_string())
        f.close()
    width, height = im.size
    if width < min_width or height < min_height:
        raise ImageException("Image too small (%dx%d < %dx%d): %s" % (width, height, min_width, min_height, response.url))


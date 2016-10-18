# -*- coding: utf-8 -*-
"""
    sphinx.util.images
    ~~~~~~~~~~~~~~~~~~

    Image utility functions for Sphinx.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import imghdr
import imagesize
from os import path

try:
    from PIL import Image        # check for the Python Imaging Library
except ImportError:
    try:
        import Image
    except ImportError:
        Image = None

mime_suffixes = {
    '.pdf': 'application/pdf',
    '.svg': 'image/svg+xml',
}


def get_image_size(filename):
    try:
        size = imagesize.get(filename)
        if size[0] == -1:
            size = None

        if size is None and Image:  # fallback to PIL
            im = Image.open(filename)
            size = im.size
            try:
                im.fp.close()
            except Exception:
                pass

        return size
    except:
        return None


def guess_mimetype(filename):
    _, ext = path.splitext(filename)
    if ext in mime_suffixes:
        return mime_suffixes[ext]
    else:
        with open(filename, 'rb') as f:
            imgtype = imghdr.what(f)
            if imgtype:
                return 'image/' + imgtype

    return None

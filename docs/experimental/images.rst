.. _topics-images:

==================
Downloading Images
==================

.. currentmodule:: scrapy.contrib.pipeline.images

Scrapy provides an :doc:`item pipeline </topics/item-pipeline>` for downloading
images attached to a particular item. For example, when you scrape products and
also want to download their images locally.

This pipeline, called the Images Pipeline and implemented in the
:class:`ImagesPipeline` class, provides a convenient way for
downloading and storing images locally with some additional features:

* Convert all downloaded images to a common format (JPG) and mode (RGB)
* Avoid re-downloading images which were downloaded recently
* Thumbnail generation
* Check images width/height to make sure they meet a minimum constraint

This pipeline also keeps an internal queue of those images which are currently
being scheduled for download, and connects those items that arrive containing
the same image, to that queue. This avoids downloading the same image more than
once when it's shared by several items.


Using the Images Pipeline
=========================

The typical workflow, when using the :class:`ImagesPipeline` goes like
this:

1. In a Spider, you scrape an item and put the URLs of its images into a
   pre-defined field, for example ``image_urls``.

2. The item is returned from the spider and goes to the item pipeline.

3. When the item reaches the :class:`ImagesPipeline`, the URLs in the
   ``image_urls`` attribute are scheduled for download using the standard
   Scrapy scheduler and downloader (which means the scheduler and downloader
   middlewares are reused), but higher priority to process them before other
   pages to scrape. The item remains "locked" at that particular pipeline stage
   until the images have finish downloading (or fail for some reason).

4. When the images finish downloading (or fail for some reason) the images gets
   another field populated with the data of the images downloaded, for example,
   ``images``. This attribute is a list of dictionaries containing information
   about the image downloaded, such as the downloaded path, and the original
   scraped url. This images in the list of the ``images`` field retains the
   same order of the original ``image_urls`` field, which is useful if you
   decide to use the first image in the list as the primary image.

.. setting:: IMAGES_DIR

The first thing we need to do is tell the pipeline where to store the
downloaded images, by setting :setting:`IMAGES_DIR`::

   IMAGES_DIR = '/path/to/valid/dir'

Then, as seen on the workflow, the pipeline will get the URLs of the images to
download from the item. In order to do this, you must override the
:meth:`~ImagesPipeline.get_media_requests` method and return a Request for each
image URL::

   def get_media_requests(self, item, info):
       for image_url in item['image_urls']:
           yield Request(image_url)

Those requests will be processed by the pipeline, and they have finished
downloading the results will be sent to the
:meth:`~ImagesPipeline.item_completed` method, as a list of dictionaries. Each
dictionary will contain status and information about the download, and the list
of dictionaries will retain the original order of the requests returned from
the :meth:`~ImagesPipeline.get_media_requests` method::

   results = [(True, 'path#checksum'), ..., (False, Failure)]

There is one additional method: :meth:`~ImagesPipeline.item_completed` which
must return the output value that will be sent to further item pipeline stages,
so you must return (or drop) the item as in any pipeline.

We will override it to store the resulting image paths (passed in results) back
in the item::

   # XXX: improve this example and add a condition for dropping images
   def item_completed(self, results, item, info):
       item['image_paths'] = [result.split('#')[0] for succes, result in results if succes]

       return item

So, the complete example of our pipeline looks like this::

   from scrapy.contrib.pipeline.images import ImagesPipeline

   # XXX: improve this example and add a condition for dropping images

   class MyImagesPipeline(ImagesPipeline):

       def get_media_requests(self, item, info):
           for image_url in item['image_urls']:
               yield Request(image_url)

       def item_completed(self, results, item, info):
           item['image_paths'] = [result.split('#')[0] for succes, result in results if succes]

           return item

.. _topics-images-expiration:

Image expiration
-----------------

.. setting:: IMAGES_EXPIRES

The Image Pipeline avoids downloading images that were downloaded recently. To
adjust this delay use the :setting:`IMAGES_EXPIRES` setting, which specifies
the delay in days::

    # 90 days of delay for image expiration
    IMAGES_EXPIRES = 90

.. _topics-images-thumbnails:

Thumbnail generation
--------------------

The Images Pipeline can automatically create thumbnails of the downloaded
images.

In order use this feature you must set the :attr:`~ImagesPipeline.THUMBS`
to a tuple of ``(size_name, (width, height))`` tuples.

The `Python Imaging Library`_ is used for thumbnailing, so you need that
library.

.. _Python Imaging Library: http://www.pythonware.com/products/pil/

Here are some examples examples.

Using numeric names::

   THUMBS = (
       ('50', (50, 50)),
       ('110', (110, 110)),
   )

Using textual names::

   THUMBS = (
       ('small', (50, 50)),
       ('big', (270, 270)),
   )

When you use this feature, the Images Pipeline will create thumbnails of the
each specified size with this format::

    IMAGES_DIR/thumbs/<image_id>/<size_name>.jpg
  
Where:

* ``<image_id>`` is the `SHA1 hash`_ of the image url
* and ``<size_name>`` is the one specified in ``THUMBS`` attribute

.. _SHA1 hash: http://en.wikipedia.org/wiki/SHA_hash_functions

Example with previous THUMB attribute::

   IMAGES_DIR/thumbs/63bbfea82b8880ed33cdb762aa11fab722a90a24/50.jpg
   IMAGES_DIR/thumbs/63bbfea82b8880ed33cdb762aa11fab722a90a24/110.jpg
   IMAGES_DIR/thumbs/63bbfea82b8880ed33cdb762aa11fab722a90a24/270.jpg


.. _topics-images-size:

Checking image size
-------------------

.. setting:: IMAGES_MIN_HEIGHT

.. setting:: IMAGES_MIN_WIDTH

You can drop images which are too small, by specifying the minimum allowed size
in the :setting:`IMAGES_MIN_HEIGHT` and :setting:`IMAGES_MIN_WIDTH` settings.

For example::

   IMAGES_MIN_HEIGHT = 110
   IMAGES_MIN_WIDTH = 110


.. _ref-images:

API Reference
=============

.. module:: scrapy.contrib.pipeline.images
   :synopsis: Images Pipeline

ImagesPipeline
--------------

.. class:: ImagesPipeline

   A pipeline to download images attached to items, for example product images.

   To enable this pipeline you must set :setting:`IMAGES_DIR` to a valid
   directory that will be used for storing the downloaded images.

   .. method:: store_image(key, image, buf, info)
 
      Override this method with specific code to persist an image.

      This method is used to persist the full image and any defined
      thumbnail, one a time.

      Return value is ignored.


   .. method:: stat_key(key, info)
 
      Override this method with specific code to stat an image.

      This method should return and dictionary with two parameters:

      * ``last_modified``: the last modification time in seconds since the epoch
      * ``checksum``: the md5sum of the content of the stored image if found

      If an exception is raised or ``last_modified`` is ``None``, then the image
      will be re-downloaded.

      If the difference in days between last_modified and now is greater than
      :setting:`IMAGES_EXPIRES` settings, then the image will be re-downloaded

      The checksum value is appended to returned image path after a hash sign
      (#), if ``checksum`` is ``None``, then nothing is appended including the
      hash sign.

   .. method:: get_media_requests(item, info)

      Return a list of Request objects to download images for this item.

      Must return ``None`` or an iterable.

      By default it returns ``None`` (no images to download).

   .. method:: item_completed(results, item, info)

      Method called when all image requests for a single item have been
      downloaded (or failed).

      The output of this method is used as the output of the Image Pipeline
      stage.

      This method typically returns the item itself or raises a
      :exc:`~scrapy.core.exceptions.DropItem` exception.

      By default, it returns the item.

   .. attribute:: THUMBS

      Thumbnail generation configuration, see :ref:`topics-images-thumbnails`.


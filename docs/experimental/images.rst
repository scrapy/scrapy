.. _topics-images:

.. module:: scrapy.contrib.pipeline.images
   :synopsis: Images Pipeline

===============
Handling Images
===============

In Scrapy, the recommended way of handling image downloads is using the
:class:`ImagesPipeline`. 

This pipeline provides convenient mechanisms to download and store images and
also the following features:

* Image format normalization (JPG)
* Image expiration
* Thumbnail creation
* Image size checking


Using a ImagesPipeline
=======================

The typical workflow of working with a :class:`ImagesPipeline` goes like this:

1. In a Spider, you obtain the URLs of the images to be downloaded and store
   them in an Item.

2. An :class:`ImagesPipeline` process the Item, downloads the images and stores
   back their resulting paths in the processed Item

We assume that if you're here you know how to handle the first part of the
workflow (if not, please refer to the tutorial), so let's focus on the second
part, using a :class:`ImagesPipeline`.

:class:`ImagesPipeline` is a descendant of BaseImagesPipeline which in turn is
a descendant of :class:`~scrapy.contrib.pipeline.MediaPipeline`, all of this classes provide
overrideable methods, hooks and settings to customize their behaviour.

So, for using the :class:`ImagesPipeline` you subclass it, override some
methods with custom code and set some required settings.

The first thing we need to do is tell the pipeline where to store the
downloaded images, so set :setting:`IMAGES_DIR` to a valid directory name that
will be used for this purpose::

   IMAGES_DIR = '/path/to/valid/dir'

Then, as seen on the workflow, the pipeline will get the URLs of the images to
download from the item. In order to do this, you must override the
:meth:`~scrapy.contrib.pipeline.MediaPipeline.get_media_requests` method and
return a Request for each image URL::

   def get_media_requests(self, item, info):
       for image_url in item['image_urls']:
           yield Request(image_url) 

Those requests will be processed by the pipeline, downloaded an when completed
the processed results will be sent to the
:meth:`~scrapy.contrib.pipeline.MediaPipeline.item_completed` method. 

The results will be a list of tuples, in wich each tuple indicates the sucess
of the downloading process and the stored image path concatenated with the
checksum of the image ::

   results = [(True, 'path#checksum'), ..., (False, Failure)]

The :meth:`~scrapy.contrib.pipeline.MediaPipeline.item_completed` is also in
charge of returning the output value to be used as the output of the pipeline
stage, so we must return (or drop) the item as in any pipeline.

We will override it to store the resulting image paths (passed in results) back
in the item::

   def item_completed(self, results, item, info):
       item['image_paths'] = [result.split('#')[0] for succes, result in results if succes]

       return item

.. note:: This is a simplification of the actual process, it will be described
   with more detail in upcoming sections.

So, the complete example of our pipeline looks like this::

   from scrapy.contrib.pipeline.images import ImagesPipeline

   class MyImagesPipeline(ImagesPipeline):

       def get_media_requests(self, item, info):
           for image_url in item['image_urls']:
               yield Request(image_url) 

       def item_completed(self, results, item, info):
           item['image_paths'] = [result.split('#')[0] for succes, result in results if succes]

           return item

This is the most basic use of :class:`ImagesPipeline`, see upcoming sections for more details.


.. _topics-images-expiration:

Image expiration
-----------------

XXX

.. _topics-images-thumbnails:

Creating thumbnails
-------------------

As mentioned in the features, :class:`ImagesPipeline` can create thumbnails of
the processed images. 

In order use this feature you must set the :attr:`~BaseImagesPipeline.THUMBS` to
a tuple of tuples, in wich each sub-tuple is a pair of thumb_id string and a
compatible python image library size (another tuple).  

See ``thumbnail`` method at http://www.pythonware.com/library/pil/handbook/image.htm.

Example::

   THUMBS = (
       ('50', (50, 50)),
       ('110', (110, 110)),
       ('270', (270, 270))
   )


When you use this feature, :class:`ImagesPipeline` will create thumbnails of
the specified sizes in ``IMAGES_DIR/thumbs/<image_id>/<thumb_id>.jpg``, where
``<image_id>`` is the ``sha1`` digest of the url of the image and
``<thumb_id>`` is the thumb_id string specified in THUMBS attribute.

Example with previous THUMB attribute::

   IMAGES_DIR/thumbs/image_sha1_digest/50.jpg
   IMAGES_DIR/thumbs/image_sha1_digest/110.jpg
   IMAGES_DIR/thumbs/image_sha1_digest/270.jpg


.. _topics-images-size:

Checking image size
-------------------

You can skip the processing of an image if its size is less than a specified
one. To use this set :setting:`IMAGES_MIN_HEIGHT` and/or
:setting:`IMAGES_MIN_WIDTH` to your likings::

   IMAGES_MIN_HEIGHT = 270
   IMAGES_MIN_WIDTH = 270


.. _ref-images:

Reference
=========

ImagesPipeline
--------------

.. class:: ImagesPipeline

   :class:`BaseImagesPipeline` descendant with filesystem support as
   image's store backend

   In order to enable this pipeline you must set :setting:`IMAGES_DIR` to a
   valid dirname that will be used for storing images.


BaseImagesPipeline
------------------

.. class:: BaseImagesPipeline

   :class:`~scrapy.contrib.pipeline.media.MediaPipeline` descendant that
   implements image downloading and thumbnail generation logic.

   This pipeline tries to minimize network transfers and image processing,
   doing stat of the images and determining if image is new, uptodate or
   expired.

   `'new'` images are those that pipeline never processed and needs to be
   downloaded from supplier site the first time.

   `'uptodate'` images are the ones that the pipeline processed and are still
   valid images.

   `'expired'` images are those that pipeline already processed but the last
   modification was made long time ago, so a reprocessing is recommended to
   refresh it in case of change.

   :setting:`IMAGES_EXPIRES` setting controls the maximun days since an image
   was modified to consider it `uptodate`.

   Downloaded images are skipped if sizes aren't greater than
   :setting:`IMAGES_MIN_WIDTH` and :setting:`IMAGES_MIN_HEIGHT` limit. A proper
   log messages will be printed.

   .. attribute:: THUMBS 

      Thumbnail generation configuration, see :ref:`topics-images-thumbnails`

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


.. module:: scrapy.contrib.pipeline.media
   :synopsis: Media Pipeline

MediaPipeline
-------------

.. class:: MediaPipeline

   Generic pipeline that handles the media associated with an item.

   .. method:: download(request, info)

      Defines how to request the download of media.

      Default gives high priority to media requests and use scheduler, shouldn't
      be necessary to override.

      This methods is called only if result for request isn't cached, request
      fingerprint is used as cache key.


   .. method:: media_to_download(request, info)

      Ongoing request hook pre-cache.

      This method is called every time a media is requested for download, and only
      once for the same request because return value is cached as media result.

      Returning a non-None value implies:

      * the return value is cached and piped into :meth:`item_media_downloaded`
        or :meth:`item_media_failed`
      * prevents downloading, this means calling :meth:`download` method.
      * :meth:`media_downloaded` or :meth:`media_failed` isn't called.


   .. method:: get_media_requests(item, info)

      Return a list of Request objects to download for this item.

      Should return ``None`` or an iterable.

      Defaults return ``None`` (no media to download)


   .. method:: media_downloaded(response, request, info)

      Method called on success download of media request

      Return value is cached and used as input for
      :meth:`item_media_downloaded` method.  Default implementation returns
      ``None``.

      WARNING: returning the response object can eat your memory.


   .. method:: media_failed(failure, request, info)

      Method called when media request failed due to any kind of download error.

      Return value is cached and used as input for :meth:`item_media_failed` method.

      Default implementation returns same Failure object.


   .. method:: item_media_downloaded(result, item, request, info)

      Method to handle result of requested media for item.

      ``result`` is the return value of :meth:`media_downloaded` hook, or the
      non-Failure instance returned by :meth:`media_failed` hook.

      Return value of this method isn't important and is recommended to return
      ``None``.


   .. method:: item_media_failed(failure, item, request, info)

      Method to handle failed result of requested media for item.

      result is the returned Failure instance of :meth:`media_failed` hook, or Failure
      instance of an exception raised by :meth:`media_downloaded` hook.

      Return value of this method isn't important and is recommended to return
      ``None``.


   .. method:: item_completed(results, item, info)

      Method called when all media requests for a single item has returned a result
      or failure.

      The return value of this method is used as output of pipeline stage.

      :meth:`item_completed` can return item itself or raise
      :exc:`~scrapy.core.exceptions.DropItem` exception.

      Default returns item


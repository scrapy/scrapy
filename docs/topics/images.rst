.. _topics-images:

=======================
Downloading Item Images
=======================

.. currentmodule:: scrapy.contrib.pipeline.images

Scrapy provides an :doc:`item pipeline </topics/item-pipeline>` for downloading
images attached to a particular item, for example, when you scrape products and
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

`Pillow`_ is used for thumbnailing and normalizing images to JPEG/RGB format,
so you need to install this library in order to use the images pipeline.
`Python Imaging Library`_ (PIL) should also work in most cases, but it
is known to cause troubles in some setups, so we recommend to use `Pillow`_
instead of `PIL <Python Imaging Library>`_.

.. _Pillow: https://github.com/python-imaging/Pillow
.. _Python Imaging Library: http://www.pythonware.com/products/pil/

Using the Images Pipeline
=========================

The typical workflow, when using the :class:`ImagesPipeline` goes like
this:

1. In a Spider, you scrape an item and put the URLs of its images into a
   ``image_urls`` field.

2. The item is returned from the spider and goes to the item pipeline.

3. When the item reaches the :class:`ImagesPipeline`, the URLs in the
   ``image_urls`` field are scheduled for download using the standard
   Scrapy scheduler and downloader (which means the scheduler and downloader
   middlewares are reused), but with a higher priority, processing them before other
   pages are scraped. The item remains "locked" at that particular pipeline stage
   until the images have finish downloading (or fail for some reason).

4. When the images are downloaded another field (``images``) will be populated
   with the results. This field will contain a list of dicts with information
   about the images downloaded, such as the downloaded path, the original
   scraped url (taken from the ``image_urls`` field) , and the image checksum.
   The images in the list of the ``images`` field will retain the same order of
   the original ``image_urls`` field. If some image failed downloading, an
   error will be logged and the image won't be present in the ``images`` field.


Usage example
=============

In order to use the image pipeline you just need to :ref:`enable it
<topics-images-enabling>` and define an item with the ``image_urls`` and
``images`` fields::

    import scrapy

    class MyItem(scrapy.Item):

        # ... other item fields ...
        image_urls = scrapy.Field()
        images = scrapy.Field()

If you need something more complex and want to override the custom images
pipeline behaviour, see :ref:`topics-images-override`.

.. _topics-images-enabling:

Enabling your Images Pipeline
=============================

.. setting:: IMAGES_STORE

To enable your images pipeline you must first add it to your project
:setting:`ITEM_PIPELINES` setting::

    ITEM_PIPELINES = {'scrapy.contrib.pipeline.images.ImagesPipeline': 1}

And set the :setting:`IMAGES_STORE` setting to a valid directory that will be
used for storing the downloaded images. Otherwise the pipeline will remain
disabled, even if you include it in the :setting:`ITEM_PIPELINES` setting.

For example::

   IMAGES_STORE = '/path/to/valid/dir'

Images Storage
==============

File system is currently the only officially supported storage, but there is
also (undocumented) support for `Amazon S3`_.

.. _Amazon S3: https://s3.amazonaws.com/

File system storage
-------------------

The images are stored in files (one per image), using a `SHA1 hash`_ of their
URLs for the file names.

For example, the following image URL::

    http://www.example.com/image.jpg

Whose `SHA1 hash` is::

    3afec3b4765f8f0a07b78f98c07b83f013567a0a

Will be downloaded and stored in the following file::

   <IMAGES_STORE>/full/3afec3b4765f8f0a07b78f98c07b83f013567a0a.jpg

Where:

* ``<IMAGES_STORE>`` is the directory defined in :setting:`IMAGES_STORE` setting

* ``full`` is a sub-directory to separate full images from thumbnails (if
  used). For more info see :ref:`topics-images-thumbnails`.

Additional features
===================

Image expiration
----------------

.. setting:: IMAGES_EXPIRES

The Image Pipeline avoids downloading images that were downloaded recently. To
adjust this retention delay use the :setting:`IMAGES_EXPIRES` setting, which
specifies the delay in number of days::

    # 90 days of delay for image expiration
    IMAGES_EXPIRES = 90

.. _topics-images-thumbnails:

Thumbnail generation
--------------------

The Images Pipeline can automatically create thumbnails of the downloaded
images.

.. setting:: IMAGES_THUMBS

In order use this feature, you must set :setting:`IMAGES_THUMBS` to a dictionary
where the keys are the thumbnail names and the values are their dimensions.

For example::

   IMAGES_THUMBS = {
       'small': (50, 50),
       'big': (270, 270),
   }

When you use this feature, the Images Pipeline will create thumbnails of the
each specified size with this format::

    <IMAGES_STORE>/thumbs/<size_name>/<image_id>.jpg

Where:

* ``<size_name>`` is the one specified in the :setting:`IMAGES_THUMBS`
  dictionary keys (``small``, ``big``, etc)

* ``<image_id>`` is the `SHA1 hash`_ of the image url

.. _SHA1 hash: http://en.wikipedia.org/wiki/SHA_hash_functions

Example of image files stored using ``small`` and ``big`` thumbnail names::

   <IMAGES_STORE>/full/63bbfea82b8880ed33cdb762aa11fab722a90a24.jpg
   <IMAGES_STORE>/thumbs/small/63bbfea82b8880ed33cdb762aa11fab722a90a24.jpg
   <IMAGES_STORE>/thumbs/big/63bbfea82b8880ed33cdb762aa11fab722a90a24.jpg

The first one is the full image, as downloaded from the site.

Filtering out small images
--------------------------

.. setting:: IMAGES_MIN_HEIGHT

.. setting:: IMAGES_MIN_WIDTH

You can drop images which are too small, by specifying the minimum allowed size
in the :setting:`IMAGES_MIN_HEIGHT` and :setting:`IMAGES_MIN_WIDTH` settings.

For example::

   IMAGES_MIN_HEIGHT = 110
   IMAGES_MIN_WIDTH = 110

Note: these size constraints don't affect thumbnail generation at all.

By default, there are no size constraints, so all images are processed.

.. _topics-images-override:

Implementing your custom Images Pipeline
========================================

.. module:: scrapy.contrib.pipeline.images
   :synopsis: Images Pipeline

Here are the methods that you should override in your custom Images Pipeline:

.. class:: ImagesPipeline

   .. method:: get_media_requests(item, info)

      As seen on the workflow, the pipeline will get the URLs of the images to
      download from the item. In order to do this, you must override the
      :meth:`~get_media_requests` method and return a Request for each
      image URL::

         def get_media_requests(self, item, info):
             for image_url in item['image_urls']:
                 yield scrapy.Request(image_url)

      Those requests will be processed by the pipeline and, when they have finished
      downloading, the results will be sent to the
      :meth:`~item_completed` method, as a list of 2-element tuples.
      Each tuple will contain ``(success, image_info_or_failure)`` where:

      * ``success`` is a boolean which is ``True`` if the image was downloaded
        successfully or ``False`` if it failed for some reason

      * ``image_info_or_error`` is a dict containing the following keys (if success
        is ``True``) or a `Twisted Failure`_ if there was a problem.

        * ``url`` - the url where the image was downloaded from. This is the url of
          the request returned from the :meth:`~get_media_requests`
          method.

        * ``path`` - the path (relative to :setting:`IMAGES_STORE`) where the image
          was stored

        * ``checksum`` - a `MD5 hash`_ of the image contents

      The list of tuples received by :meth:`~item_completed` is
      guaranteed to retain the same order of the requests returned from the
      :meth:`~get_media_requests` method.

      Here's a typical value of the ``results`` argument::

          [(True,
            {'checksum': '2b00042f7481c7b056c4b410d28f33cf',
             'path': 'full/7d97e98f8af710c7e7fe703abc8f639e0ee507c4.jpg',
             'url': 'http://www.example.com/images/product1.jpg'}),
           (True,
            {'checksum': 'b9628c4ab9b595f72f280b90c4fd093d',
             'path': 'full/1ca5879492b8fd606df1964ea3c1e2f4520f076f.jpg',
             'url': 'http://www.example.com/images/product2.jpg'}),
           (False,
            Failure(...))]

      By default the :meth:`get_media_requests` method returns ``None`` which
      means there are no images to download for the item.

   .. method:: item_completed(results, items, info)

      The :meth:`ImagesPipeline.item_completed` method called when all image
      requests for a single item have completed (either finished downloading, or
      failed for some reason).

      The :meth:`~item_completed` method must return the
      output that will be sent to subsequent item pipeline stages, so you must
      return (or drop) the item, as you would in any pipeline.

      Here is an example of the :meth:`~item_completed` method where we
      store the downloaded image paths (passed in results) in the ``image_paths``
      item field, and we drop the item if it doesn't contain any images::

          from scrapy.exceptions import DropItem

          def item_completed(self, results, item, info):
              image_paths = [x['path'] for ok, x in results if ok]
              if not image_paths:
                  raise DropItem("Item contains no images")
              item['image_paths'] = image_paths
              return item

      By default, the :meth:`item_completed` method returns the item.


Custom Images pipeline example
==============================

Here is a full example of the Images Pipeline whose methods are examplified
above::

    import scrapy
    from scrapy.contrib.pipeline.images import ImagesPipeline
    from scrapy.exceptions import DropItem

    class MyImagesPipeline(ImagesPipeline):

        def get_media_requests(self, item, info):
            for image_url in item['image_urls']:
                yield scrapy.Request(image_url)

        def item_completed(self, results, item, info):
            image_paths = [x['path'] for ok, x in results if ok]
            if not image_paths:
                raise DropItem("Item contains no images")
            item['image_paths'] = image_paths
            return item

.. _Twisted Failure: http://twistedmatrix.com/documents/current/api/twisted.python.failure.Failure.html
.. _MD5 hash: http://en.wikipedia.org/wiki/MD5

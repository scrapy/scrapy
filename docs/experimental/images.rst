.. _topics-images:

=======================
Downloading Item Images
=======================

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

The `Python Imaging Library`_ is used for thumbnailing and normalizing images
to JPEG/RGB format, so you need to install that library in order to use the
images pipeline.

.. _Python Imaging Library: http://www.pythonware.com/products/pil/

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
   another field populated with the path of the images downloaded, for example,
   ``image_paths``. This attribute is a list of dictionaries containing
   information about the image downloaded, such as the downloaded path, and the
   original scraped url. This images in the list of the ``image_paths`` field
   would retain the same order of the original ``image_urls`` field, which is
   useful if you decide to use the first image in the list as the primary
   image.

.. setting:: IMAGES_STORE

The first thing we need to do is tell the pipeline where to store the
downloaded images, through the :setting:`IMAGES_STORE` setting::

   IMAGES_STORE = '/path/to/valid/dir'

Then, as seen on the workflow, the pipeline will get the URLs of the images to
download from the item. In order to do this, you must override the
:meth:`~ImagesPipeline.get_media_requests` method and return a Request for each
image URL::

    def get_media_requests(self, item, info):
        for image_url in item['image_urls']:
            yield Request(image_url)

Those requests will be processed by the pipeline and, when they have finished
downloading, the results will be sent to the
:meth:`~ImagesPipeline.item_completed` method, as a list of 2-element tuples.
Each tuple will contain ``(success, image_info_or_failure)`` where:

* ``success`` is a boolean which is ``True`` if the image was downloading
  successfully or ``False`` if it failed for some reason

* ``image_info_or_error`` is a dict containing the following keys (if success
  is ``True``) or a `Twisted Failure`_ if there was a problem.

  * ``url`` - the url where the image was downloaded from. This is the url of
    the request returned from the :meth:`~ImagesPipeline.get_media_requests`
    method.

  * ``path`` - the path (relative to :setting:`IMAGES_STORE`) where the image
    was stored

  * ``checksum`` - a `MD5`_ hash of the image contents

.. _Twisted Failure: http://twistedmatrix.com/documents/8.2.0/api/twisted.python.failure.Failure.html
.. _MD5: http://en.wikipedia.org/wiki/MD5

The list of tuples received by :meth:`~ImagesPipeline.item_completed` is
guaranteed to retain the same order of the requests returned from the
:meth:`~ImagesPipeline.get_media_requests` method.
  
Here's a typical an example value of ``results`` argument::

    [(True,
      {'checksum': '2b00042f7481c7b056c4b410d28f33cf',
       'path': '7d97e98f8af710c7e7fe703abc8f639e0ee507c4.jpg',
       'url': 'http://www.example.com/images/product1.jpg'}),
     (True,
      {'checksum': 'b9628c4ab9b595f72f280b90c4fd093d',
       'path': '1ca5879492b8fd606df1964ea3c1e2f4520f076f',
       'url': 'http://www.example.com/images/product2.jpg'}),
     (False,
      Failure(...))]

The :meth:`~ImagesPipeline.item_completed` method must return the output that
will be sent to further item pipeline stages, so you must return (or drop) the
item, as you would in any pipeline.

Here is an example of :meth:`~ImagesPipeline.item_completed` method where we
store the downloaded image paths (passed in results) in the ``image_paths``
item field, and we drop the item if it doesn't contain any images::

    from scrapy.core.exceptions import DropItem

    def item_completed(self, results, item, info):
        image_paths = [info['path'] for success, info in results if success]
        if not image_paths:
            raise DropItem("Item contains no images")
        item['image_paths'] = image_paths
        return item

So, the complete example of our pipeline would look like this::

    from scrapy.contrib.pipeline.images import ImagesPipeline
    from scrapy.core.exceptions import DropItem

    class MyImagesPipeline(ImagesPipeline):

        def get_media_requests(self, item, info):
            for image_url in item['image_urls']:
                yield Request(image_url)

        def item_completed(self, results, item, info):
            image_paths = [info['path'] for success, info in results if success]
            if not image_paths:
                raise DropItem("Item contains no images")
            item['image_paths'] = image_paths
            return item

.. _topics-images-expiration:

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

In order use this feature you must set the :attr:`~ImagesPipeline.THUMBS`
to a tuple of ``(size_name, (width, height))`` tuples.

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

    IMAGES_STORE/thumbs/<image_id>/<size_name>.jpg
  
Where:

* ``<image_id>`` is the `SHA1 hash`_ of the image url
* ``<size_name>`` is the one specified in the ``THUMBS`` attribute

.. _SHA1 hash: http://en.wikipedia.org/wiki/SHA_hash_functions

Example with using ``50`` and ``110`` thumbnail names::

   IMAGES_STORE/thumbs/63bbfea82b8880ed33cdb762aa11fab722a90a24/50.jpg
   IMAGES_STORE/thumbs/63bbfea82b8880ed33cdb762aa11fab722a90a24/110.jpg

Example with using ``small`` and ``big`` thumbnail names::

   IMAGES_STORE/thumbs/63bbfea82b8880ed33cdb762aa11fab722a90a24/small.jpg
   IMAGES_STORE/thumbs/63bbfea82b8880ed33cdb762aa11fab722a90a24/big.jpg

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

   To enable this pipeline you must set :setting:`IMAGES_STORE` to a valid
   directory that will be used for storing the downloaded images. Otherwise the
   pipeline will remain disabled, even if you include it in the
   :setting:`ITEM_PIPELINES` setting.

   .. method:: get_media_requests(item, info)

      Return a list of Request objects to download images for this item.

      Must return ``None`` or an iterable.

      By default it returns ``None`` which means there are no images to
      download for the item.

   .. method:: item_completed(results, item, info)

      Method called when all image requests for a single item have been
      downloaded (or failed).

      The output of this method is used as the output of the Image Pipeline
      stage.

      This method must returns the item itself or raise a
      :exc:`~scrapy.core.exceptions.DropItem` exception.

      By default, it returns the item.

   .. attribute:: THUMBS

      List of thumbnails to generate for the images. See
      :ref:`topics-images-thumbnails`.


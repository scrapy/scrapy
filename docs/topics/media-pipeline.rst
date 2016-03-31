.. _topics-media-pipeline:

===========================================
Downloading and processing files and images
===========================================

.. currentmodule:: scrapy.pipelines.images

Scrapy provides reusable :doc:`item pipelines </topics/item-pipeline>` for
downloading files attached to a particular item (for example, when you scrape
products and also want to download their images locally). These pipelines share
a bit of functionality and structure (we refer to them as media pipelines), but
typically you'll either use the Files Pipeline or the Images Pipeline.

Both pipelines implement these features:

* Avoid re-downloading media that was downloaded recently
* Specifying where to store the media (filesystem directory, Amazon S3 bucket)

The Images Pipeline has a few extra functions for processing images:

* Convert all downloaded images to a common format (JPG) and mode (RGB)
* Thumbnail generation
* Check images width/height to make sure they meet a minimum constraint

The pipelines also keep an internal queue of those media URLs which are currently
being scheduled for download, and connect those responses that arrive containing
the same media to that queue. This avoids downloading the same media more than
once when it's shared by several items.

Using the Files Pipeline
========================

The typical workflow, when using the :class:`FilesPipeline` goes like
this:

1. In a Spider, you scrape an item and put the URLs of the desired into a
   ``file_urls`` field.

2. The item is returned from the spider and goes to the item pipeline.

3. When the item reaches the :class:`FilesPipeline`, the URLs in the
   ``file_urls`` field are scheduled for download using the standard
   Scrapy scheduler and downloader (which means the scheduler and downloader
   middlewares are reused), but with a higher priority, processing them before other
   pages are scraped. The item remains "locked" at that particular pipeline stage
   until the files have finish downloading (or fail for some reason).

4. When the files are downloaded, another field (``files``) will be populated
   with the results. This field will contain a list of dicts with information
   about the downloaded files, such as the downloaded path, the original
   scraped url (taken from the ``file_urls`` field) , and the file checksum.
   The files in the list of the ``files`` field will retain the same order of
   the original ``file_urls`` field. If some file failed downloading, an
   error will be logged and the file won't be present in the ``files`` field.


Using the Images Pipeline
=========================

Using the :class:`ImagesPipeline` is a lot like using the :class:`FilesPipeline`,
except the default field names used are different: you use ``image_urls`` for
the image URLs of an item and it will populate an ``images`` field for the information
about the downloaded images.

The advantage of using the :class:`ImagesPipeline` for image files is that you
can configure some extra functions like generating thumbnails and filtering
the images based on their size.

The Images Pipeline uses `Pillow`_ for thumbnailing and normalizing images to
JPEG/RGB format, so you need to install this library in order to use it.
`Python Imaging Library`_ (PIL) should also work in most cases, but it is known
to cause troubles in some setups, so we recommend to use `Pillow`_ instead of
PIL.

.. _Pillow: https://github.com/python-pillow/Pillow
.. _Python Imaging Library: http://www.pythonware.com/products/pil/


.. _topics-media-pipeline-enabling:

Enabling your Media Pipeline
============================

.. setting:: IMAGES_STORE
.. setting:: FILES_STORE

To enable your media pipeline you must first add it to your project
:setting:`ITEM_PIPELINES` setting.

For Images Pipeline, use::

    ITEM_PIPELINES = {'scrapy.pipelines.images.ImagesPipeline': 1}

For Files Pipeline, use::

    ITEM_PIPELINES = {'scrapy.pipelines.files.FilesPipeline': 1}


.. note::
    You can also use both the Files and Images Pipeline at the same time.


Then, configure the target storage setting to a valid value that will be used
for storing the downloaded images. Otherwise the pipeline will remain disabled,
even if you include it in the :setting:`ITEM_PIPELINES` setting.

For the Files Pipeline, set the :setting:`FILES_STORE` setting::

   FILES_STORE = '/path/to/valid/dir'

For the Images Pipeline, set the :setting:`IMAGES_STORE` setting::

   IMAGES_STORE = '/path/to/valid/dir'

Supported Storage
=================

File system is currently the only officially supported storage, but there is
also (undocumented) support for storing files in `Amazon S3`_.

.. _Amazon S3: https://aws.amazon.com/s3/

File system storage
-------------------

The files are stored using a `SHA1 hash`_ of their URLs for the file names.

For example, the following image URL::

    http://www.example.com/image.jpg

Whose `SHA1 hash` is::

    3afec3b4765f8f0a07b78f98c07b83f013567a0a

Will be downloaded and stored in the following file::

   <IMAGES_STORE>/full/3afec3b4765f8f0a07b78f98c07b83f013567a0a.jpg

Where:

* ``<IMAGES_STORE>`` is the directory defined in :setting:`IMAGES_STORE` setting
  for the Images Pipeline.

* ``full`` is a sub-directory to separate full images from thumbnails (if
  used). For more info see :ref:`topics-images-thumbnails`.


Usage example
=============

.. setting:: FILES_URLS_FIELD
.. setting:: FILES_RESULT_FIELD
.. setting:: IMAGES_URLS_FIELD
.. setting:: IMAGES_RESULT_FIELD

In order to use a media pipeline first, :ref:`enable it
<topics-media-pipeline-enabling>`.

Then, if a spider returns a dict with the URLs key (``file_urls`` or
``image_urls``, for the Files or Images Pipeline respectively), the pipeline will
put the results under respective key (``files`` or ``images``).

If you prefer to use :class:`~.Item`, then define a custom item with the
necessary fields, like in this example for Images Pipeline::

    import scrapy

    class MyItem(scrapy.Item):

        # ... other item fields ...
        image_urls = scrapy.Field()
        images = scrapy.Field()

If you want to use another field name for the URLs key or for the results key,
it is also possible to override it.

For the Files Pipeline, set :setting:`FILES_URLS_FIELD` and/or
:setting:`FILES_RESULT_FIELD` settings::

    FILES_URLS_FIELD = 'field_name_for_your_files_urls'
    FILES_RESULT_FIELD = 'field_name_for_your_processed_files'

For the Images Pipeline, set :setting:`IMAGES_URLS_FIELD` and/or
:setting:`IMAGES_RESULT_FIELD` settings::

    IMAGES_URLS_FIELD = 'field_name_for_your_images_urls'
    IMAGES_RESULT_FIELD = 'field_name_for_your_processed_images'

If you need something more complex and want to override the custom pipeline
behaviour, see :ref:`topics-media-pipeline-override`.


Additional features
===================

File expiration
---------------

.. setting:: IMAGES_EXPIRES
.. setting:: FILES_EXPIRES

The Image Pipeline avoids downloading files that were downloaded recently. To
adjust this retention delay use the :setting:`FILES_EXPIRES` setting (or
:setting:`IMAGES_EXPIRES`, in case of Images Pipeline), which
specifies the delay in number of days::

    # 120 days of delay for files expiration
    FILES_EXPIRES = 120

    # 30 days of delay for images expiration
    IMAGES_EXPIRES = 30

The default value for both settings is 90 days.

.. _topics-images-thumbnails:

Thumbnail generation for images
-------------------------------

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

.. _SHA1 hash: https://en.wikipedia.org/wiki/SHA_hash_functions

Example of image files stored using ``small`` and ``big`` thumbnail names::

   <IMAGES_STORE>/full/63bbfea82b8880ed33cdb762aa11fab722a90a24.jpg
   <IMAGES_STORE>/thumbs/small/63bbfea82b8880ed33cdb762aa11fab722a90a24.jpg
   <IMAGES_STORE>/thumbs/big/63bbfea82b8880ed33cdb762aa11fab722a90a24.jpg

The first one is the full image, as downloaded from the site.

Filtering out small images
--------------------------

.. setting:: IMAGES_MIN_HEIGHT

.. setting:: IMAGES_MIN_WIDTH

When using the Images Pipeline, you can drop images which are too small, by
specifying the minimum allowed size in the :setting:`IMAGES_MIN_HEIGHT` and
:setting:`IMAGES_MIN_WIDTH` settings.

For example::

   IMAGES_MIN_HEIGHT = 110
   IMAGES_MIN_WIDTH = 110

.. note::
    The size constraints don't affect thumbnail generation at all.

It is possible to set just one size constraint or both. When setting both of
them, only images that satisfy both minimum sizes will be saved. For the
above example, images of sizes (105 x 105) or (105 x 200) or (200 x 105) will
all be dropped because at least one dimension is shorter than the constraint.

By default, there are no size constraints, so all images are processed.

.. _topics-media-pipeline-override:

Extending the Media Pipelines
=============================

.. module:: scrapy.pipelines.files
   :synopsis: Files Pipeline

See here the methods that you can override in your custom Files Pipeline:

.. class:: FilesPipeline

   .. method:: FilesPipeline.get_media_requests(item, info)

      As seen on the workflow, the pipeline will get the URLs of the images to
      download from the item. In order to do this, you can override the
      :meth:`~get_media_requests` method and return a Request for each
      file URL::

         def get_media_requests(self, item, info):
             for file_url in item['file_urls']:
                 yield scrapy.Request(file_url)

      Those requests will be processed by the pipeline and, when they have finished
      downloading, the results will be sent to the
      :meth:`~item_completed` method, as a list of 2-element tuples.
      Each tuple will contain ``(success, file_info_or_error)`` where:

      * ``success`` is a boolean which is ``True`` if the image was downloaded
        successfully or ``False`` if it failed for some reason

      * ``file_info_or_error`` is a dict containing the following keys (if success
        is ``True``) or a `Twisted Failure`_ if there was a problem.

        * ``url`` - the url where the file was downloaded from. This is the url of
          the request returned from the :meth:`~get_media_requests`
          method.

        * ``path`` - the path (relative to :setting:`FILES_STORE`) where the file
          was stored

        * ``checksum`` - a `MD5 hash`_ of the image contents

      The list of tuples received by :meth:`~item_completed` is
      guaranteed to retain the same order of the requests returned from the
      :meth:`~get_media_requests` method.

      Here's a typical value of the ``results`` argument::

          [(True,
            {'checksum': '2b00042f7481c7b056c4b410d28f33cf',
             'path': 'full/0a79c461a4062ac383dc4fade7bc09f1384a3910.jpg',
             'url': 'http://www.example.com/files/product1.pdf'}),
           (False,
            Failure(...))]

      By default the :meth:`get_media_requests` method returns ``None`` which
      means there are no files to download for the item.

   .. method:: FilesPipeline.item_completed(results, items, info)

      The :meth:`FilesPipeline.item_completed` method called when all file
      requests for a single item have completed (either finished downloading, or
      failed for some reason).

      The :meth:`~item_completed` method must return the
      output that will be sent to subsequent item pipeline stages, so you must
      return (or drop) the item, as you would in any pipeline.

      Here is an example of the :meth:`~item_completed` method where we
      store the downloaded file paths (passed in results) in the ``file_paths``
      item field, and we drop the item if it doesn't contain any files::

          from scrapy.exceptions import DropItem

          def item_completed(self, results, item, info):
              file_paths = [x['path'] for ok, x in results if ok]
              if not file_paths:
                  raise DropItem("Item contains no files")
              item['file_paths'] = file_paths
              return item

      By default, the :meth:`item_completed` method returns the item.


.. module:: scrapy.pipelines.images
   :synopsis: Images Pipeline

See here the methods that you can override in your custom Images Pipeline:

.. class:: ImagesPipeline

    The :class:`ImagesPipeline` is an extension of the :class:`FilesPipeline`,
    customizing the field names and adding custom behavior for images.

   .. method:: ImagesPipeline.get_media_requests(item, info)

      Works the same way as :meth:`FilesPipeline.get_media_requests` method,
      but using a different field name for image urls.

      Must return a Request for each image URL.

   .. method:: ImagesPipeline.item_completed(results, items, info)

      The :meth:`ImagesPipeline.item_completed` method is called when all image
      requests for a single item have completed (either finished downloading, or
      failed for some reason).

      Works the same way as :meth:`FilesPipeline.item_completed` method,
      but using a different field names for storing image downloading results.

      By default, the :meth:`item_completed` method returns the item.


Custom Images pipeline example
==============================

Here is a full example of the Images Pipeline whose methods are examplified
above::

    import scrapy
    from scrapy.pipelines.images import ImagesPipeline
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

.. _Twisted Failure: https://twistedmatrix.com/documents/current/api/twisted.python.failure.Failure.html
.. _MD5 hash: https://en.wikipedia.org/wiki/MD5

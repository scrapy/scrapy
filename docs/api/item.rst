========
Item API
========

Items
=====

.. class:: scrapy.Item([arg])

    Return a new Item optionally initialized from the given argument.

    Items replicate the standard `dict`_ class, including its constructor. The
    only additional attribute provided by Items is
    :func:`~scrapy.item.Item.fields`.

    .. attribute:: fields

        A dictionary containing *all declared fields* for this Item, not only
        those populated. The keys are the field names and the values are the
        :class:`Field` objects used in the :ref:`Item declaration
        <topics-items-declaring>`.


Fields
======

.. class:: scrapy.Field([arg])

    The :class:`Field` class is just an alias to the built-in `dict`_ class and
    doesn't provide any extra functionality or attributes. In other words,
    :class:`Field` objects are plain-old Python dicts. A separate class is used
    to support the :ref:`item declaration syntax <topics-items-declaring>`
    based on class attributes.


Item Loaders
============

.. automodule:: scrapy.loader
   :members:

.. automodule:: scrapy.loader.processors
   :members:


Item Pipelines
==============

.. automodule:: scrapy.pipelines
   :members:

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

   .. method:: FilesPipeline.item_completed(results, item, info)

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

   .. method:: ImagesPipeline.item_completed(results, item, info)

      The :meth:`ImagesPipeline.item_completed` method is called when all image
      requests for a single item have completed (either finished downloading, or
      failed for some reason).

      Works the same way as :meth:`FilesPipeline.item_completed` method,
      but using a different field names for storing image downloading results.

      By default, the :meth:`item_completed` method returns the item.

.. automodule:: scrapy.pipelines.media
   :members:


Item Exporters
==============

.. automodule:: scrapy.exporters
   :members:


.. _dict: https://docs.python.org/library/stdtypes.html#dict
.. _MD5 hash: https://en.wikipedia.org/wiki/MD5
.. _Twisted Failure: https://twistedmatrix.com/documents/current/api/twisted.python.failure.Failure.html

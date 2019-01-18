========
Item API
========

Items
=====

.. class:: scrapy.item.Field
.. autoclass:: scrapy.Field
   :members:

.. class:: scrapy.item.Item
.. autoclass:: scrapy.Item
   :inherited-members:

   ..
        The fields attribute documentation below is copy-pasted from the source
        code because a Sphinx bug prevents it from being displayed otherwise:
        https://github.com/sphinx-doc/sphinx/issues/741

   .. attribute:: fields

        A dictionary containing *all declared fields* for this Item, not only
        those populated. The keys are the field names and the values are the
        :class:`Field` objects used in the :ref:`Item declaration
        <topics-items-declaring>`.


Item Loaders
============

.. autoclass:: scrapy.loader.ItemLoader
   :members:


Processors
----------

.. automodule:: scrapy.loader.processors
   :members:


Item Pipelines
==============

.. seealso:: :ref:`topics-item-pipeline`

Built-in pipelines
------------------

.. autoclass:: scrapy.pipelines.files.FilesPipeline
   :members:

.. autoclass:: scrapy.pipelines.images.ImagesPipeline
   :members:

.. autoclass:: scrapy.pipelines.media.MediaPipeline
   :members:

Interface
---------

.. autointerface:: scrapy.interfaces.IPipeline
   :members:


Manager
-------

.. automodule:: scrapy.pipelines
   :members:
   :undoc-members:


.. _topics-exporters-reference:

Item Exporters
==============

.. automodule:: scrapy.exporters
   :members:


.. _MD5 hash: https://en.wikipedia.org/wiki/MD5
.. _Twisted Failure: https://twistedmatrix.com/documents/current/api/twisted.python.failure.Failure.html

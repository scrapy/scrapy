========
Item API
========

Items
=====

.. autoclass:: scrapy.Field
    :members:

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

``scrapy.loader.processors``
''''''''''''''''''''''''''''

.. automodule:: scrapy.loader.processors
   :members:


Item Pipelines
==============

.. autointerface:: scrapy.interfaces.IPipeline
    :members:

.. automodule:: scrapy.pipelines
   :members:

.. autoclass:: scrapy.pipelines.files.FilesPipeline
   :members:

.. autoclass:: scrapy.pipelines.images.ImagesPipeline
   :members:

.. autoclass:: scrapy.pipelines.media.MediaPipeline
   :members:


.. _topics-exporters-reference:

Item Exporters
==============

.. automodule:: scrapy.exporters
   :members:


.. _dict: https://docs.python.org/library/stdtypes.html#dict
.. _MD5 hash: https://en.wikipedia.org/wiki/MD5
.. _Twisted Failure: https://twistedmatrix.com/documents/current/api/twisted.python.failure.Failure.html

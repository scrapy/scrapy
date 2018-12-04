.. _topics-api-settings:

============
Settings API
============

.. module:: scrapy.settings
   :synopsis: Settings manager

.. attribute:: SETTINGS_PRIORITIES

    Dictionary that sets the key name and priority level of the default
    settings priorities used in Scrapy.

    Each item defines a settings entry point, giving it a code name for
    identification and an integer priority. Greater priorities take more
    precedence over lesser ones when setting and retrieving values in the
    :class:`~scrapy.settings.Settings` class.

    .. highlight:: python

    ::

        SETTINGS_PRIORITIES = {
            'default': 0,
            'command': 10,
            'project': 20,
            'spider': 30,
            'cmdline': 40,
        }

    For a detailed explanation on each settings sources, see:
    :ref:`topics-settings`.

.. autofunction:: get_settings_priority

.. autoclass:: Settings
   :show-inheritance:
   :members:

.. autoclass:: BaseSettings
   :members:

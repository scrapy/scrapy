=============
Extension API
=============

.. automodule:: scrapy.extension
   :members:

.. _topics-extensions-ref:

Built-in extensions
===================

General purpose extensions
--------------------------

LogStats
''''''''

.. autoclass:: scrapy.extensions.logstats.LogStats


CoreStats
'''''''''

.. autoclass:: scrapy.extensions.corestats.CoreStats


.. _topics-extensions-ref-telnetconsole:

TelnetConsole
'''''''''''''

.. module:: scrapy.extensions.telnet
   :synopsis: The Telnet Console

.. autoclass:: TelnetConsole

This extension exposes the following signal:

.. autofunction:: update_telnet_vars(telnet_vars)


.. _topics-extensions-ref-memusage:

MemoryUsage
'''''''''''

.. autoclass:: scrapy.extensions.memusage.MemoryUsage


MemoryDebugger
''''''''''''''

.. autoclass:: scrapy.extensions.memdebug.MemoryDebugger


CloseSpider
'''''''''''

.. autoclass:: scrapy.extensions.closespider.CloseSpider


StatsMailer
'''''''''''

.. autoclass:: scrapy.extensions.statsmailer.StatsMailer


Debugging extensions
--------------------

StackTraceDump
''''''''''''''

.. autoclass:: scrapy.extensions.debug.StackTraceDump


Debugger
''''''''

.. autoclass:: scrapy.extensions.debug.Debugger

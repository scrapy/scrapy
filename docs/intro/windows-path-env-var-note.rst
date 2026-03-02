.. note::

   If you see a message like ``'scrapy' is not recognized as an internal or external command``
   when trying to run the ``scrapy`` command-line tool, it usually means that the
   Python ``Scripts`` directory is not in your system ``PATH``.

   To make the ``scrapy`` command available, add the ``Scripts`` directory of your
   Python installation to the ``PATH`` environment variable.

   As a workaround, you can run ``python -m scrapy <arguments>`` instead (for example,
   ``python -m scrapy startproject myproject``).

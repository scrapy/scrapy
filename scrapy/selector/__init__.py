"""
XPath selectors

To select the backend explicitly use the SCRAPY_SELECTORS_BACKEND environment
variable.

Two backends are currently available: lxml (default) and libxml2.

"""

import os

backend = os.environ.get('SCRAPY_SELECTORS_BACKEND')

if backend == 'libxml2':
    from scrapy.selector.libxml2sel import *
elif backend == 'lxml':
    from scrapy.selector.lxmlsel import *
else:
    try:
        import lxml
    except ImportError:
        import libxml2
        from scrapy.selector.libxml2sel import *
    else:
        from scrapy.selector.lxmlsel import *

"""
XPath selectors

Two backends are currently available: libxml2 and lxml

To select the backend explicitly use the SELECTORS_BACKEND variable in your
project. Otherwise, libxml2 will be tried first. If libxml2 is not available,
lxml will be used.
"""

from scrapy.conf import settings

if settings['SELECTORS_BACKEND'] == 'lxml':
    from scrapy.selector.lxmlsel import *
elif settings['SELECTORS_BACKEND'] == 'libxml2':
    from scrapy.selector.libxml2sel import *
elif settings['SELECTORS_BACKEND'] == 'dummy':
    from scrapy.selector.dummysel import *
else:
    try:
        import lxml
    except ImportError:
        try:
            import libxml2
        except ImportError:
            from scrapy.selector.dummysel import *
        else:
            from scrapy.selector.libxml2sel import *
    else:
        from scrapy.selector.lxmlsel import *

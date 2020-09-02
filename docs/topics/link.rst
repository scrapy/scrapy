.. _topics-link:

====
Link
====

Link objects represent an extracted link by the :class:`~scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor`.

The ``__init__`` method of
:class:`scrapy.link.Link` takes values that describe structure of the anchor tag that makes
up the link. :class:`LxmlLinkExtractor.extract_links
<scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor.extract_links>` returns a
list of matching :class:`scrapy.link.Link` objects from a
:class:`~scrapy.http.Response` object.


Link
----

.. module:: scrapy.link
   :synopsis: Link from link extractors


.. class:: Link(url, text='', fragment='', nofollow=False)

    Using the anchor tag sample below to illustrate the parameters::

            <a href="/nofollow.html#foo" rel="nofollow">Dont follow this one</a>


    :param url: the address being linked to in the anchor tag. From the sample, this is ``base_url/nofollow.html``.
    :type url: str

    :param text: the text in the anchor tag. From the sample, this is ``Dont follow this one``.
    :type text: str

    :param fragment: the part of the url after the hash symbol. From the sample, this is ``foo``.
    :type fragment: str

    :param nofollow: an indication of the presence or absence of a nofollow value in the ``rel`` attribute
                    of the anchor tag.
    :type nofollow: boolean

.. _scrapy.link: https://github.com/scrapy/scrapy/blob/master/scrapy/link.py

.. _extraction:

===================================
Extracting clean content and values
===================================

Sometimes what you want out of a page is the page itself, without navigation,
ads or footers, as the input of a search index, a summarizer or a
retrieval-augmented generation (RAG) pipeline. See :ref:`clean-content`.

Sometimes you know which parts of the page you want, you have already
:ref:`selected <topics-selectors>` them, and what you have is a string that is
not a value yet: a price with a currency symbol on it, a date written in
Spanish, a phone number written however its owner felt like. See
:ref:`parsing-values`.

.. _clean-content:

Clean content
=============

Trafilatura_ turns HTML into text or markdown, dropping boilerplate. Call it
on :attr:`response.text <scrapy.http.TextResponse.text>` from a callback:

.. skip: next
.. code-block:: python

    import scrapy
    import trafilatura


    class ContentSpider(scrapy.Spider):
        name = "content"
        allowed_domains = ["quotes.toscrape.com"]
        start_urls = ["https://quotes.toscrape.com/"]

        def parse(self, response):
            yield {
                "url": response.url,
                "content": trafilatura.extract(response.text, output_format="markdown"),
            }
            yield from response.follow_all(css="a", callback=self.parse)

Save that as :file:`content.py` and write the whole crawl to a JSON Lines
file:

.. code-block:: shell

    scrapy runspider content.py -O content.jsonl

Title, author, date and site name come from a second call, which roughly
triples the time spent on each page, so ask for them only if you need them:

.. skip: next
.. code-block:: python

    metadata = trafilatura.extract_metadata(response.text)
    yield {
        "url": response.url,
        "title": metadata.title,
        "date": metadata.date,
        "content": trafilatura.extract(response.text, output_format="markdown"),
    }

Where the content is not prose
------------------------------

Trafilatura is tuned for articles, and it keeps what it is confident about.
On a product page or a listing, where most of the page is not prose, it often
returns a fraction of what you were after, or nothing at all.

There the answer is to :ref:`select <topics-selectors>` the parts you want.
For a part that is itself rich content, such as a product description or the
body of a post, clear-html_ normalizes the selected node into clean HTML or
text, keeping embedded images and videos:

.. skip: start

.. code-block:: pycon

    >>> from clear_html import clean_node, cleaned_node_to_html
    >>> from clear_html import cleaned_node_to_text
    >>> node = clean_node(response.css("article")[0].root, response.url)
    >>> cleaned_node_to_html(node)
    '<article>\n\n<p>Hi <strong>there</strong></p>\n\n</article>'
    >>> cleaned_node_to_text(node)
    'Hi there'

.. skip: end

Pages you cannot download as they are
-------------------------------------

If the content is not in the HTML that Scrapy downloads, it is loaded
dynamically; see :ref:`topics-dynamic-content`.

If the website answers your requests with an error page or a challenge
instead of the content, see :ref:`bans`.

`Zyte API`_ covers both, and through `scrapy-zyte-api`_ it can also return
the content already structured: its article extraction gives you the text of
an article and a simplified HTML version of its body, which markdownify_
turns into markdown:

.. skip: start

.. code-block:: pycon

    >>> from markdownify import markdownify
    >>> article = response.raw_api_response["article"]
    >>> markdownify(article["articleBodyHtml"])
    'Hi **there**'

.. skip: end

.. _parsing-values:

Parsing values
==============

The following libraries turn a selected string into a value. They also work
as :ref:`input processors <topics-loaders-processors>`.

.. skip: start

-   extruct_ reads JSON-LD, microdata, RDFa, Open Graph and Dublin Core out of
    a page, which is often the cheapest source of a title, an author or a
    date:

    .. code-block:: pycon

        >>> import extruct
        >>> data = extruct.extract(response.text, base_url=response.url)
        >>> data["opengraph"][0]["properties"]
        [('og:title', 'Hi there')]

-   dateparser_ reads a date written in prose, in any of the languages it
    supports:

    .. code-block:: pycon

        >>> import dateparser
        >>> dateparser.parse("12 de octubre de 2025")
        datetime.datetime(2025, 10, 12, 0, 0)

-   `price-parser`_ separates the amount of a price from its currency:

    .. code-block:: pycon

        >>> from price_parser import Price
        >>> Price.fromstring("1.199,00 €")
        Price(amount=Decimal('1199.00'), currency='€')

    For numbers written out in words, use `number-parser`_ instead.

-   `zyte-parsers`_ parses fields out of a selected node: breadcrumbs, GTIN,
    rating, review count, brand and, building on `price-parser`_, price.

    .. code-block:: pycon

        >>> from zyte_parsers import extract_breadcrumbs
        >>> extract_breadcrumbs(response.css("nav")[0], base_url=response.url)
        (Breadcrumb(name='Books', url='https://example.com/books'),)

-   phonenumbers_ turns a phone number as written into E.164, given the
    region it belongs to:

    .. code-block:: pycon

        >>> import phonenumbers
        >>> number = phonenumbers.parse("0664 123 4567", "AT")
        >>> phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
        '+436641234567'

-   ftfy_ repairs text that reached you as mojibake:

    .. code-block:: pycon

        >>> import ftfy
        >>> ftfy.fix_text("The Mona Lisa doesnâ€™t have eyebrows.")
        "The Mona Lisa doesn't have eyebrows."

-   py3langid_ tells you which language a text is in:

    .. code-block:: pycon

        >>> import py3langid
        >>> py3langid.classify("Dieser Text ist auf Deutsch geschrieben.")
        ('de', -154.48843383789062)

.. skip: end

To parse a value out of JavaScript code in the page, see
:ref:`topics-parsing-javascript`.

.. _clear-html: https://github.com/zytedata/clear-html
.. _dateparser: https://github.com/scrapinghub/dateparser
.. _extruct: https://github.com/scrapinghub/extruct
.. _ftfy: https://github.com/rspeer/python-ftfy
.. _markdownify: https://github.com/matthewwithanm/python-markdownify
.. _number-parser: https://github.com/scrapinghub/number-parser
.. _phonenumbers: https://github.com/daviddrysdale/python-phonenumbers
.. _price-parser: https://github.com/scrapinghub/price-parser
.. _py3langid: https://github.com/adbar/py3langid
.. _scrapy-zyte-api: https://github.com/scrapy-plugins/scrapy-zyte-api
.. _Trafilatura: https://trafilatura.readthedocs.io/en/latest/
.. _Zyte API: https://docs.zyte.com/zyte-api/get-started.html
.. _zyte-parsers: https://github.com/zytedata/zyte-parsers

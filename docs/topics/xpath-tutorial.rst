==============
XPath Tutorial
==============

Part 1: What is XPath?
======================

XPath is a language
-------------------

.. epigraph::

   *"XPath is a language for addressing parts of an XML document"*

   -- `XML Path Language 1.0 <https://www.w3.org/TR/xpath/>`__

This abstract from the official specifications says it all:

-  *"XPath is a language"*: an XPath expression is a character string...
-  *"for addressing parts of an XML document"*: ...a string that that
   you pass to an XPath engine acting over an XML (or HTML) document,
   outputting parts of it, and following the data model explained below.

Why learn XPath?
----------------

-  with XPath, you can navigate **everywhere** inside a DOM tree
-  it's a must-have skill for accurate web data extraction
-  XPath is more powerful than CSS selectors
-  it allows selection and filtering with a fine-grained look at the
   text content
-  XPath allows complex conditioning with axes
-  XPath is extensible with custom functions (we won’t cover that in
   this tutorial though)

XPath data model
----------------

XPath's `data model <http://www.w3.org/TR/xpath/#data-model>`__ is a
tree of nodes representing a document. Nodes can be either:

-  **element nodes** (``<p>This is a paragraph</p>``),
-  or **attribute nodes** (``href="page.html"`` inside an ``<a>`` tag),
-  or **text nodes** (``"I have something to say"``),
-  or **comment nodes** (``<!-- a comment -->``),
-  (or root nodes, or namespace nodes, or processing instructions nodes
   but we will not cover them here.)

In XPath's data model, everything is a node : elements, attributes,
comments... (**but not all nodes are elements.**)

And nodes have an order, the **document order**: the order in which they
appear in the XML/HTML source.

In effect, this data model allows you to represent everything inside an
XML or HTML document, in a structured, ordered and hierarchical way.

Throughout this tutorial, we'll use the following sample HTML page to
illustrate how XPath works:

::

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type">
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>

Here is an ASCII tree representation of our toy HTML document for an
XPath engine, according to the data model:

::

    # 0--(ROOT)
     +-- # 1--<html>
         +-- # 2--(TXT): '\n'
         +-- # 3--<head>
         |   +-- # 4--(TXT): '\n  '
         |   +-- # 5--<title>
         |   |   +-- # 6--(TXT): 'This is a title'
         |   +-- # 7--(TXT): '\n  '
         |   +-- # 8--<meta>
         |   |   +-- # 9--(ATTR): content: 'text/html; charset=utf-8'
         |   |   +-- #10--(ATTR): http-equiv: 'content-type'
         |   +-- #11--(TXT): '\n'
         +-- #12--(TXT): '\n'
         +-- #13--<body>
         |   +-- #14--(TXT): '\n  '
         |   +-- #15--<div>
         |   |   +-- #16--(TXT): '\n    '
         |   |   +-- #17--<div>
         |   |   |   +-- #18--(TXT): '\n      '
         |   |   |   +-- #19--<p>
         |   |   |   |   +-- #20--(TXT): 'This is a paragraph.'
         |   |   |   +-- #21--(TXT): '\n      '
         |   |   |   +-- #22--<p>
         |   |   |   |   +-- #23--(TXT): 'Is this '
         |   |   |   |   +-- #24--<a>
         |   |   |   |   |   +-- #25--(ATTR): href: 'page2.html'
         |   |   |   |   |   +-- #26--(TXT): 'a link'
         |   |   |   |   +-- #27--(TXT): '?'
         |   |   |   +-- #28--(TXT): '\n      '
         |   |   |   +-- #29--<br>
         |   |   |   +-- #30--(TXT): '\n      Apparently.\n    '
         |   |   +-- #31--(TXT): '\n    '
         |   |   +-- #32--<div>
         |   |   |   +-- #33--(ATTR): class: 'second'
         |   |   |   +-- #34--(TXT): '\n      Nothing to add.\n      Except maybe this '
         |   |   |   +-- #35--<a>
         |   |   |   |   +-- #36--(ATTR): href: 'page3.html'
         |   |   |   |   +-- #37--(TXT): 'other link'
         |   |   |   +-- #38--(TXT): '. \n      '
         |   |   |   +-- #39--(COMM): ' And this comment '
         |   |   |   +-- #40--(TXT): '\n    '
         |   |   +-- #41--(TXT): '\n  '
         |   +-- #42--(TXT): '\n'
         +-- #43--(TXT): '\n'

You can see various tree branches and leaves:

-  e.g. ``<div>`` or ``<p>``: these are element nodes
-  ``(TXT)`` represent text nodes
-  ``(ATTR)`` represent attribute nodes
-  ``(COMM)`` represent comment nodes

The ``#<number>`` are the document orders of each node.

.. note::
    You can also notice that **text with only whitespace** (space and
    newlines in our example) **are proper nodes**, they do have their
    document order and can be selected with XPath.

In-browser widget and using parsel
----------------------------------

To illustrate and learn XPath, we will use an in-browser widget
allowing you to play around with XPath expressions and see the output
live.
We will also illustrate some Python pattern for data extraction with
XPath using the `parsel <https://github.com/scrapy/parsel>`__ library
which powers Scrapy selectors under the hood.
It is a Python module written on top of `lxml <http://lxml.de/>`__.

.. note::
    lxml itself is built using the C library `libxml2 <http://www.xmlsoft.org/>`__,
    which has a conformant XPath 1.0 engine.
    You should be able to run the same XPath expressions with
    any XPath 1.0 engine, and get the same results.

This tutorial only showcases XPath 1.0. (`XPath has reached version 3
<https://www.w3.org/TR/xpath-3/>`__, but you can already do a
lot with XPath 1.0 and Python. And there's no XPath>1.0 implementation
in Python today.)

When showing Python code snippets using Parsel, we assume that we have
a ``Selector`` -- called ``doc`` -- created with the HTML content, similarly
to the following:

.. code:: python

    import parsel


    htmlsample = '''<html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>'''

    #
    # Below is a small "hack" to change the representation of extracted
    #  nodes when using parsel.
    # This is to represent return values as serialized HTML element or
    # string, and not parsel's wrapper objects.
    #
    parsel.Selector.__str__ = parsel.Selector.extract
    parsel.Selector.__repr__ = parsel.Selector.__str__
    parsel.SelectorList.__repr__ = lambda x: '[{}]'.format(
        '\n '.join("({}) {!r}".format(i, repr(s))
                   for i, s in enumerate(x, start=1))
    ).replace(r'\n', '\n')

    doc = parsel.Selector(text=htmlsample)

XPath return types
------------------

When applied over a document, an XPath expression can return either:

-  a node-set -- this is the most common case, and often it's a set of
   element nodes
-  a string
-  a number (floating point)
-  a boolean

.. note::
    **When an XPath expression returns a node-set, you do get a set of
    nodes, even if there's only one node in the set.**
    With parsel, you get a ``list`` of nodes though, not a Python ``set``.

XPath expressions
-----------------

We will now take a look at some example XPath expressions to get a
feeling of how they work. We'll explain the syntax in more details later
on.

XPath expressions are passed to an XPath engine as strings.


Selecting the root node of a document (warning: special case)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The root node is a special node: this is a quote from XPath 1.0 specs:

    *"The root node is the root of the tree. A root node does not occur
    except as the root of the tree. The element node for the document
    element is a child of the root node."*

Selecting the root node of a document with XPath is one of the shortest
XPath expressions: ``"/"`` (a string with only a forward slash).

.. xpathdemo:: /

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>

This is very similar to ``cd /`` in a shell within a Unix filesystem
(going to the root directory).

.. warning::
    Unfortunately, this ``"/"`` expression does not work as expected
    with parsel. We get an empty list instead of the root node.

    It is a limitation of lxml apparently, because
    it works with libxml2 directly. In practice though, this doesn't matter
    much because the root node is virtually never used directly.


Selecting elements
~~~~~~~~~~~~~~~~~~

Elements build the structure and hierarchy of the document. An element
in HTML (and XML) is what you see in the source code between an opening
and corresponding closing tag, and everything in between.

-  ``<title>This is a title</title>`` is a ``title`` element,
-  ``<p>Is this <a href="page2.html">a link</a>?</p>`` is a ``p``
   (paragraph) element.

Selecting elements is probably the most common use-case for XPath on
HTML documents.

Elements can have children -- the root node being the ancestor of them
all. Their children can also have children and so on. Sometimes,
elements only have one child. This hierarchy forms a family tree of nodes.

.. note::
    **Text nodes are not elements.** (They are still nodes, obviously.)
    They do not have children nodes, but they are always children
    of some element.

    Therefore, text nodes are always leaves of the document tree.

We said earlier that the document element is a child of the root node.
In fact, the document element is the only child of the root node. And
for our sample HTML document, it's the top-level ``<html>...</html>`` element.
Still, selecting it will return a single-node node-set, the XPath expression
being ``/*``:

.. xpathdemo:: /*

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>

The asterisk here, ``*``, means "any element". And ``/*`` means "any
element under the root node". HTML documents have only one element like
this: the ``<html>`` element.

Another example: how to get ``<title>`` elements? Use ``/html/head/title``:

.. xpathdemo:: /html/head/title

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>

Again, if you are familiar with the Unix filesystem, you probably
intuitively understand what this does:

* start from the root (of the document)

    * select the ``<html>`` node (with ``/html``)

        * select the ``<head>`` node under the ``<html>`` node
          (appending ``/head``)

            * select the ``<title>`` node under the ``<head>`` node
              (appending ``/title``)

In other words, the XPath expression represents the path from the root
node down to the target node(s). Parts of this path are read **from left to right**,
and represent a top-to-bottom direction in the document tree.

Much like a Unix filepath represents the path from the filesystem's root
to the target file(s) or directory(ies).
There's one major difference with a Unix filesystem though: in an HTML
or XML document, an element can have multiple children with the same name.
For example, the ``<div>`` just under the ``<body>`` has 2 ``<div>`` children:

.. xpathdemo:: /html/body/div/div

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>

Another example is getting the paragraphs inside the first child of that
``<div>`` under ``<body>``, there are two of them:

.. xpathdemo:: /html/body/div/div[1]/p

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>

Here we're introducing a **positional predicate**, ``[1]``. The ``div[1]``
part means *"the first <div> child under its parent"*.

If you recall, earlier we used a ``*`` asterisk to mean *any element*.
There are other elements with those two paragraphs under that very
``<div>``. Let's try and select all of them, regardless of their name:

.. xpathdemo:: /html/body/div/div[1]/*

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>

.. note::
    Continuing the filesystem anamogy, ``*`` is similar in effect to what
    you can do in a Unix shell to find files or directories without explicit
    full names.

See the ``<br/>`` being selected? It's an empty element (i.e. with node children)
but it is there nonetheless.

Selecting text nodes
~~~~~~~~~~~~~~~~~~~~

If we stay around these ``<p>`` and ``<br>`` elements, you may have noticed
that the ASCII tree representation from the beginning also shows some text after the
``<br/>`` break: the string ``"Apparently."``. It is a text node.

Selecting text nodes is a bit different than selecting elements:
you use the special ``text()`` syntax. Let's try it by replacing the last
part of our last XPath expression, forming ``/html/body/div/div[1]/text()``:

.. xpathdemo:: /html/body/div/div[1]/text()

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>

You may have expected only one text result, the last one, ``"Apparently."``.
But we got four! And three of them are blank even. Why is that?

In fact, HTML authors usually indent their tags with whitespace for
readability. This does not usually change the layout in your browser.
But this **whitespace counts as text nodes** for XPath's data model,
it is not stripped nor filtered.

Let's represent that ``<div>`` as a Python string as it appears in the
HTML source::

    #
    #   text node #1                       text node #2                                           text node #3
    #     <------>                           <------>                                               <------>
    '<div>\n      <p>This is a paragraph.</p>\n      <p>Is this <a href="page2.html">a link</a>?</p>\n      <br>\n  Apparently.\n    </div>'


We've marked the first three text nodes before the non-whitespace only
text node.

Another example is to get the text nodes of ``<title>`` elements
(remember that ``<title>`` is an element, and that it happens it
contains a text node, with the string content "This is a title"):

.. xpathdemo:: /html/head/title/text()

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>

.. note::
    Again, there's only one ``<title>``, and it contains only one text node,
    but selecting text nodes in ``<title>`` returns a single string-value
    in a list, not one string.


Selecting nodes without a full, explicit path
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

What we did until now is tell the XPath engine how to get to nodes,
node by node, from parent to child, from root node down to target nodes.
This assumes that you know the hierarchy of nodes beforehand.
This *can* be the case, but most often than not,
either you do not know or you do not want to indicate all the steps from
the root node down to the node(s) you are interested in (this can be
very error prone -- have you put enough ``div/div/div...``?).

XPath provides a handy shortcut when you do not know at what level you
expect your target node to be.
Say for example that we want to select all ``<p>`` paragraph elements
inside the ``<body>``. We don't *a-priori* know what their parent node is.
(For all we know, they can be anywhere under the ``<body>`` element.)
The shortcut to use is ``//`` (two forward slashes).
Let's try this: ``//body//p``

.. xpathdemo:: //body//p

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>

So we got 2 paragraphs, what we expected.

This also works for text nodes (there are a lot of them in our sample
document!). Try ``//body//text()``:

.. xpathdemo:: //body//text()

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>


Selecting attributes
~~~~~~~~~~~~~~~~~~~~

Elements can also have attributes.
In our sample document, we have two ``<a>`` elements, each with a
``href`` attribute. There's also a ``<meta>`` element with two
attributes: ``content`` and ``http-equiv``.

This is how you can select these attributes, with an ``@`` prefix before
the attribute name:

.. xpathdemo:: //a/@href

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>


.. xpathdemo:: //meta/@*

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>


The ``*`` (asterisk) here after ``@`` means the same thing as in ``/*``
exept that this is for attributes, and not elements: meaning that you
want any attributes, whatever their name.


Get a string representation of an element
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The XPath language also comes with a few string functions, that you can
wrap around an XPath expression selecting elements:

.. xpathdemo:: string(/html/head/title)

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>


This example uses ``string(<xpathexpression>)``, one of several handy
`functions <https://www.w3.org/TR/xpath/#section-String-Functions>`__ in XPath.
``string()`` will concatenate all text content from the selected node
and all of its children, recursively, effectively stripping HTML tags.

You may wonder what's the difference between ``string(/html/head/title)``
and ``/html/head/title/text()`` from earlier? Here, in fact, you get the same
result because ``<title>`` only has one child text node.
(Concatenating this list of one text node is the same as getting it
directly with ``text()`` at the end.)

But string functions can be very handy when you apply them on nodes that
have multiple children and multiple text node children or descendant.
What happens when you apply ``string()`` on the document ``<body>`` for example?
You get a text representation of the document, without the tags:


.. xpathdemo:: string(string(//body))

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>


Counting elements
~~~~~~~~~~~~~~~~~

We said earlier that XPath expressions could also return numbers.
One example of this is counting the number of paragraphs in the
document:

.. xpathdemo:: count(//p)

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>

.. note::
    With parsel, you get a floating point number back, and in the form of a
    string. This is specific to parsel. Another XPath engine might return a
    native floating point number.

Another example: get the number of attributes in the document (whatever
their parent element):


.. xpathdemo:: count(//@*)

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>



Boolean operations
~~~~~~~~~~~~~~~~~~

XPath expressions can also return booleans. This is not that usueful
by itself, but it becomes handy when used in predicates (that we will
cover a bit later).

For example, testing the number of paragraphs:


.. xpathdemo:: count(//p) = 2

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>

.. xpathdemo:: count(//p) = 42

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>


Part 2: Location Paths: how to move inside the document tree
============================================================

A **Location path** is the most common XPath expression.
It is used to move in any direction from a starting point (*the context
node*) to any node(s) in the tree:

-  It is a string, with a series of **“location steps”**:
   ``"step1 / step2 / step3 ..."``;
-  It represents the **selection and filtering of nodes**, processed step by
   step, **from left to right**;
-  Each step is of the form ``axis :: nodetest [predicate]*``

   - an *axis* (implicit or explicit),
   - a *node test*,
   - zero or more *predicates*.

So the examples we saw earlier are (or contain) an XPath location path:
``/html/head/title``, ``//body//p`` etc.

.. tip::
    Whitespace does NOT matter in XPath.

    (Except for ``“//”`` and ``“..”``;
    ``“/   /”`` and ``“.  .”`` are syntax errors.)

    For example, the following three expressions produce the same result:

    .. code:: pycon

        >>> doc.xpath('/html/head/title')
        [(1) '<title>This is a title</title>']

    .. code:: pycon

        >>> doc.xpath('/    html   / head   /title')
        [(1) '<title>This is a title</title>']



    .. code:: pycon

        >>> doc.xpath('''
        ...     /html
        ...         /head
        ...             /title''')
        [(1) '<title>This is a title</title>']

    So **don’t be afraid to indent your XPath expressions to improve
    readability.**

Relative vs. absolute paths
---------------------------

Location paths can be relative or absolute:

-  ``"step1/step2/step3"`` is relative
-  ``"/step1/step2/step3"`` is absolute

In other words, an absolute path is a relative path starting with "/" (forward slash).
Absolute paths are relative to the root node.

.. tip::
    Use relative paths whenever possible. This prevents unexpected
    selection of duplicate nodes in loop iterations.

    For example, in our sample document, only one ``<div>`` contains
    paragraphs. Looping on each ``<div>`` and using the absolute location
    path ``//p`` will produce the same result for each iteration: returning
    ALL paragraphs in the document everytime.

    .. code:: pycon

        >>> for div in doc.xpath('//body//div'):
        ...     print(div.xpath('//p'))
        [(1) '<p>This is a paragraph.</p>'
         (2) '<p>Is this <a href="page2.html">a link</a>?</p>']
        [(1) '<p>This is a paragraph.</p>'
         (2) '<p>Is this <a href="page2.html">a link</a>?</p>']
        [(1) '<p>This is a paragraph.</p>'
         (2) '<p>Is this <a href="page2.html">a link</a>?</p>']


    Compare this with using the relative ``'p'`` or ``'./p'`` expression
    that will only look at children ``<p>`` under each ``<div>``, and only
    one of those ``<div>`` will show having paragraphs as shown below:

    .. code:: pycon

        >>> for div in doc.xpath('//body//div'):
        ...     print(div.xpath('p'))
        []
        [(1) '<p>This is a paragraph.</p>'
         (2) '<p>Is this <a href="page2.html">a link</a>?</p>']
        []

    .. code:: pycon

        >>> for div in doc.xpath('//body//div'):
        ...     print(div.xpath('./p'))
        []
        [(1) '<p>This is a paragraph.</p>'
         (2) '<p>Is this <a href="page2.html">a link</a>?</p>']
        []


Abbreviated syntax vs. full syntax
----------------------------------

What we’ve seen earlier is in fact the “`abbreviated syntax
<https://www.w3.org/TR/xpath/#path-abbrev>`__” for XPath
expressions. The full syntax is quite verbose (but you sometimes need it):

.. list-table::
   :header-rows: 1

   * - Abbreviated syntax
     - Full syntax
   * - ``/html/head/title``
     - ``/child::html /child:: head /child:: title``
   * - ``//meta/@content``
     - ``/descendant-or-self::node() /child::meta / attribute::content``
   * - ``//div/div[@class="second"]``
     - ``/descendant-or-self::node() /child::div /child::div [attribute::class = "second"]``
   * - ``//div/a/text()``
     - ``/descendant-or-self::node() /child::div /child::a /child::text()``

What are these ``child::``, ``descendant-or-self::`` and
``attribute::``, you may ask? They are axes.

Axes: moving around
-------------------

.. important::
    Remember that each step of an XPath location path is of the form
    ``AXIS :: nodetest [predicate]*``.

    The "axis" is the first part of each location path step. It can be
    explicit, or implicit in abbreviated syntax. For example, in
    ``/html/head/title``, the ``child::`` axis is omitted in each step.

    In this section, we'll use explicit axes as much as we can.

**Axes give the direction to go next, one location step at a time.**

-  ``self`` (where you are)
-  ``parent``, ``child`` (direct hop up or down the document tree)
-  ``ancestor``, ``ancestor-or-self``, ``descendant``,
   ``descendant-or-self`` (multi-hop)
-  ``following``, ``following-sibling``, ``preceding``,
   ``preceding-sibling`` (document order)
-  ``attribute``, ``namespace`` (non-element)

Stay where you are: self
~~~~~~~~~~~~~~~~~~~~~~~~

Let's assume that we have selected the first ``<div>`` element in our
sample document, the one just under the ``<body>`` element:

.. code:: pycon

    >>> first_div = doc.xpath('//body/div')[0]
    >>> first_div
    <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>



The ``self`` axis represents *the context node*, i.e. where you are
currently in the Location Path steps. (This may not sound very useful,
but we will see later when this can be handy.)

.. code:: pycon

    >>> first_div.xpath('self::*')
    [(1) '<div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>']



If you chain ``self::`` steps, you'll stay on the same context node:

.. code:: pycon

    >>> first_div.xpath('self::*/self::*/self::*')
    [(1) '<div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>']



``self::`` is usually seen in abbreviated form, i.e. in '.' (one dot)
which means ``self::node()``.
So you could also use:

.. code:: pycon

    >>> first_div.xpath('.')
    [(1) '<div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>']

.. code:: pycon

    >>> first_div.xpath('././.')
    [(1) '<div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>']


Move up or down the tree: child, descendant, parent, ancestor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``child`` axis is for immediate children nodes of the context node.
Here, our context node ``<div>`` has two ``<div>`` children:

.. code:: pycon

    >>> first_div.xpath('child::*')
    [(1) '<div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>'
     (2) '<div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>']


``child`` is in fact the default axis, hence it can be omitted (e.g. we
saw that ``/html/head/title`` is equivalent of
``/child::html/child::head/child::title``.)

The ``parent`` axis is the dual of ``child``: you go up one level in the
document tree:

.. code:: pycon

    >>> first_div.xpath('parent::*')
    [(1) '<body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>']

There's an alias for ``parent::``: it's ``..`` (two dots, much like in a
Unix filesystem):

.. code:: pycon

    >>> first_div.xpath('..')
    [(1) '<body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>']


Let's simplify our ASCII tree representation from earlier to only
consider element nodes:

::

    # 0--(ROOT)
     +-- # 1--<html>
         +-- # 3--<head>
         |   +-- # 5--<title>
         |   +-- # 8--<meta>
         +-- #13--<body>
             +-- #15--<div>
                 +-- #17--<div>
                 |   +-- #19--<p>
                 |   +-- #22--<p>
                 |   |   +-- #24--<a>
                 |   +-- #29--<br>
                 +-- #32--<div>
                     +-- #35--<a>

With this simplified tree representation, this is what ``self``,
``child`` and ``parent`` select:

::

                    # 0--(ROOT)
                     +-- # 1--<html>
                         +-- # 3--<head>
                         |   +-- # 5--<title>
                         |   +-- # 8--<meta>
    parent::* ---------> +-- #13--<body>
                             |
    self::* ------------->   +-- #15--<div>
                                 |
    child::*----+----------->    +-- #17--<div>
                |                |   +-- #19--<p>
                |                |   +-- #22--<p>
                |                |   |   +-- #24--<a>
                |                |   +-- #29--<br>
                +----------->    +-- #32--<div>
                                     +-- #35--<a>

Recursively go up or down
^^^^^^^^^^^^^^^^^^^^^^^^^

The ``descendant`` axis is similar to ``child`` but also goes deeper down
the tree, looking at children of each child, recursively:

.. code:: pycon

    >>> first_div.xpath('descendant::*')
    [(1) '<div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>'
     (2) '<p>This is a paragraph.</p>'
     (3) '<p>Is this <a href="page2.html">a link</a>?</p>'
     (4) '<a href="page2.html">a link</a>'
     (5) '<br>'
     (6) '<div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>'
     (7) '<a href="page3.html">other link</a>']


You might guess already what ``ancestor`` is for: it is the dual axis of
``descendant``. It goes to the parent of the context node, the parent of
this parent, the parent of the parent of this parent, etc.

.. code:: pycon

    >>> first_div.xpath('ancestor::*')
    [(1) '<html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type">
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>'
     (2) '<body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>']



Special case of ``descendant-or-/ancestor-or-self`` axes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The last axes to be aware of when you need to move up or down the document
tree are ``descendant-or-self`` and ``ancestor-or-self``.
They are the same as ``descendant`` or ``ancestor`` except they also
include the context node.

.. code:: pycon

    >>> first_div.xpath('./descendant-or-self::node()/text()')
    [(1) '
        '
     (2) '
          '
     (3) 'This is a paragraph.'
     (4) '
          '
     (5) 'Is this '
     (6) 'a link'
     (7) '?'
     (8) '
          '
     (9) '
          Apparently.
        '
     (10) '
        '
     (11) '
          Nothing to add.
          Except maybe this '
     (12) 'other link'
     (13) '.
          '
     (14) '
        '
     (15) '
      ']


Move "sideways": children nodes of the same parent
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If nodes can have parents, children, ancestors and descendants, they can
also have siblings (to continue the family analogy). **Siblings are
nodes that have the same parent node.**

Some siblings may come before the context node (they appear before in
the document, their order is lower), or they can come after the context
node. There are two axis for these two directions: ``preceding-sibling`` and
``following-sibling``.

Let's first select this paragraph from our sample document:
``<p>Is this <a href="page2.html">a link</a>?</p>``. It's the 2nd child
of the 1st ``<div>`` of the ``<div>`` we used above:

.. code:: python

    paragraph = first_div.xpath('child::div[1]/child::p[2]')[0]

Here we started using 2 new patterns along with the axes:

-  ``child::div`` vs. ``child::*``:

   - ``*`` means "any element node" (this is a *node-test* that we'll cover afterwards),
   - while ``child::div`` means "any child that is a ``<div>`` element".

-  ``[1]`` and ``[2]``: which mean *first* and *second* in the current
   step's node-set (this is a kind of *predicate* that we'll cover
   afterwards also)

.. code:: pycon

    >>> paragraph.xpath('preceding-sibling::*')
    [(1) '<p>This is a paragraph.</p>']



.. code:: pycon

    >>> paragraph.xpath('following-sibling::*')
    [(1) '<br>']



Again, let's see which elements were selected in our ASCII tree
representation:

::

                    # 0--(ROOT)
                     +-- # 1--<html>
                         +-- # 3--<head>
                         |   +-- # 5--<title>
                         |   +-- # 8--<meta>
                         +-- #13--<body>
                             |
                             +-- #15--<div>
                                 |
                                 +-- #17--<div>
                                 |   |
                                 |   |
    preceding-sibling::* ----------> +-- #19--<p>
                                 |   |
                                 |   |
    self::* -----------------------> +-- #22--<p>
                                 |   |   |
                                 |   |   +-- #24--<a>
                                 |   |
                                 |   |
    following-sibling::* ----------> +-- #29--<br>
                                 |
                                 |
                                 +-- #32--<div>
                                     +-- #35--<a>

Earlier we were also able to get text nodes that were siblings of these
``<p>`` elements. Why did they not get selected?

The reason is that ``child::*`` means "any child *element*", not "any node."
(Remember that text nodes are not elements.)

To also get text node siblings, you need to use either ``child::text()``
or ``child::node()``. (But we may be getting ahead of ourselves with *node tests*.)

.. code:: pycon

    >>> paragraph.xpath('following-sibling::node()')
    [(1) '
          '
     (2) '<br>'
     (3) '
          Apparently.
        ']

.. code:: pycon

    >>> paragraph.xpath('following-sibling::text()')
    [(1) '
          '
     (2) '
          Apparently.
        ']



Nodes before and after, in document order
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``preceding`` and ``following`` are two special axes that do not look at
the tree hierarchy, but work on the document order of nodes.

.. important::
    Remember, all nodes in XPath data model have an order, called the
    *document order*. Node 1 is the first node in the HTML source, node 2 is
    the node appearing next etc.

    ::

          #1    #2    #3   ...
        <html><head><title>...

.. code:: pycon

    >>> paragraph.xpath('preceding::*')
    [(1) '<head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type">
    </head>'
     (2) '<title>This is a title</title>'
     (3) '<meta content="text/html; charset=utf-8" http-equiv="content-type">'
     (4) '<p>This is a paragraph.</p>']



.. code:: pycon

    >>> paragraph.xpath('following::*')
    [(1) '<br>'
     (2) '<div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>'
     (3) '<a href="page3.html">other link</a>']


This is what these axes select in our ASCII-tree representation:

::

                    # 0--(ROOT)
                     +-- # 1--<html>
                         |   |
                    +--> +-- # 3--<head>
                    |    |   |
                    +------> +-- # 5--<title>
                    |    |   |
                    +------> +-- # 8--<meta>
                    |    |
                    |    +-- #13--<body>
                    |        |
                    |        +-- #15--<div>
                    |            |
                    |            +-- #17--<div>
                    |            |   |
                    |            |   |
    preceding::* ---+--------------> +-- #19--<p>
                                 |   |
                                 |   |
    self::* -----------------------> +-- #22--<p>
                                 |   |   |
                                 |   |   +-- #24--<a>
                                 |   |
                                 |   |
    following::* -----------+------> +-- #29--<br>
                            |    |
                            |    |
                            +--> +-- #32--<div>
                            |        |
                            +------> +-- #35--<a>

.. note::
    Notice that ``preceding`` does not include ancestors and ``following``
    does not include descendants.
    This property `is mentioned in XPath specs <https://www.w3.org/TR/xpath/#axes>`__
    like this:

        *"The ancestor, descendant, following, preceding and self axes
        partition a document (ignoring attribute and namespace nodes): they
        do not overlap and together they contain all the nodes in the
        document."*

    In other words::

        document == self ∪ (ancestor ∪ preceding) ∪ (descendant ∪ following)

    (``∪`` denoting the "union" for node-sets.)

Node tests
----------

.. important::
    A "node test" is the second part of each step in a location path.

    ::

        axis :: NODETEST [predicate]*

    Node tests select node types along the step's axis.

a node test can be:

-  a *name test*:

    -  such as ``p``, ``title`` or ``a`` for elements: ``/html/head/title``
       contains 3 steps, each with a *name test* node-test
    -  or ``href`` or ``src`` for attributes: ``/a/@href`` selects "href"
       attributes of ``<a>`` elements

-  a *node type test*:

    -  ``node()``: any node type
    -  ``text()``: text nodes
    -  ``comment()``: comment nodes
    -  ``*`` (an asterisk): the meaning depends on the axis:

       -  an ``*`` step alone selects any element node
       -  an ``@*`` selects any attribute node

.. warning::
    ``text()`` is not a function call that converts a node to it's
    text representation, it's just a test on the node type.

    Compare these two expressions:

    .. code:: pycon

        >>> paragraph.xpath('child::text()')
        [(1) 'Is this '
         (2) '?']

    .. code:: pycon

        >>> paragraph.xpath('string(self::*)')
        [(1) 'Is this a link?']

    ``child::text()`` selects all children nodes that are also text nodes.

    The "a" string is part of the ``<a>`` inside the paragraph, so it's not selected.
    It is not a direct child of the ``<p>`` element.

    Whereas ``string(self::*)`` applies to the paragraph (the context node,
    selected with ``self::*``) and recursively gets text content of
    children, children of children and so on.

Predicates
----------

.. important::
    Predicates are the last part of each step in a location path. Predicates
    are optional.
    ::

        axis :: nodetest [PREDICATE]*

    They are used to further filter nodes on properties that cannot be
    expressed with the step's axis and node test.

Remember that XPath location paths work step by step. Each step produces
a node-set for each node from the previous step's node-set, with
possibly more than 1 node in each node set.

You may not be interested in all nodes from a node test. And predicates
are used to tell the XPath engine the condition(s) they should meet.

The syntax for predicates is simple: just surround conditions within
square brackets. What's inside the square brackets can be:

-  a number (see positional predicates below)
-  a location path: the predicate will select nodes for which the
   location path matches at least a node
-  a boolean operation: for example to test a condition on text content
   or count of children

Positional predicates
~~~~~~~~~~~~~~~~~~~~~

The first use-case is selecting nodes based on their position in a
node-set.

Node-sets order depends on the axis, but let's consider that
the order of a node in a node-set is the document order.

Let's say we don't want the two paragraphs in the ``<div>`` we looked at
earlier, only the first one:

.. code:: pycon

    >>> doc.xpath('//body/div/div/p')
    [(1) '<p>This is a paragraph.</p>'
     (2) '<p>Is this <a href="page2.html">a link</a>?</p>']


.. xpathdemo:: //body/div/div/p[1]

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>


If you want the last node in a node-set, you can use ``last()``:

.. xpathdemo:: //body/div/div[last()]

    <html>
    <head>
      <title>This is a title</title>
      <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    </head>
    <body>
      <div>
        <div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br />
          Apparently.
        </div>
        <div class="second">
          Nothing to add.
          Except maybe this <a href="page3.html">other link</a>.
          <!-- And this comment -->
        </div>
      </div>
    </body>
    </html>


.. warning::
    Because location paths work step by step, from left to right,
    positional predicates are about the **position of a node in a node-set
    produced by the current step**,
    not about the position of the node in the document tree.

    For example, ``//body//div[1]`` is NOT the first ``<div>`` under the
    ``<body>`` element; it will select **all** ``<div>`` that are the first
    child of their parent:

    .. xpathdemo:: //body//div[1]

        <html>
        <head>
          <title>This is a title</title>
          <meta content="text/html; charset=utf-8" http-equiv="content-type" />
        </head>
        <body>
          <div>
            <div>
              <p>This is a paragraph.</p>
              <p>Is this <a href="page2.html">a link</a>?</p>
              <br />
              Apparently.
            </div>
            <div class="second">
              Nothing to add.
              Except maybe this <a href="page3.html">other link</a>.
              <!-- And this comment -->
            </div>
          </div>
        </body>
        </html>

    This becomes more apparent when you expand the expression to its
    full syntax::

        /descendant-or-self::node()
            /child::body
                /descendant-or-self::node()
                                       ^
                                       |
                    # first child of this parent
                    /child::div[1]


    You can however select the first ``<div>`` (in document order)
    in a ``<body>`` using parentheses to group nodes into a new node-set:

    - first select all ``<div>`` elements -- ``//body//div``,
    - then group them -- ``( //body//div )``,
    - and finally select the first one -- ``( //body//div ) [1]``,

    .. xpathdemo:: ( //body//div ) [1]

        <html>
        <head>
          <title>This is a title</title>
          <meta content="text/html; charset=utf-8" http-equiv="content-type" />
        </head>
        <body>
          <div>
            <div>
              <p>This is a paragraph.</p>
              <p>Is this <a href="page2.html">a link</a>?</p>
              <br />
              Apparently.
            </div>
            <div class="second">
              Nothing to add.
              Except maybe this <a href="page3.html">other link</a>.
              <!-- And this comment -->
            </div>
          </div>
        </body>
        </html>

Position ranges
^^^^^^^^^^^^^^^

TODO: things like ``//table/tbody/tr[position() > 2]``

Location paths as predicates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

TODO: things like ``//table[tr/div/a]``

Boolean predicates
~~~~~~~~~~~~~~~~~~

TODO: things like ``//table[count(tr)=10]``

Special case of string value tests
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

TODO: things like ``//table[.//img/@src="pic.png"]`` or
``//table[th="Some headers"]``

Special trick for testing multiple node names
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This is when ``self::`` axis can be helpful.

TODO: things like ``./descendant-or-self::*[self::ul or self::ol]``

Nested predicates
~~~~~~~~~~~~~~~~~

We said that location paths can be used as predicate. And location paths
can have predicates. So it's possible to end up with nested predicates.
(And that's ok.)

.. code:: pycon

    >>> #                <------predicate --------->
    >>> #                    <-nested predicate->
    >>> doc.xpath('//div[p  [a/@href="page2.html"]  ]')
    [(1) '<div>
          <p>This is a paragraph.</p>
          <p>Is this <a href="page2.html">a link</a>?</p>
          <br>
          Apparently.
        </div>']



In fact, the above is equivalent to ``//div[p/a/@href="page2.html"]``
with no nesting:

    .. xpathdemo:: //div[p/a/@href="page2.html"]

        <html>
        <head>
          <title>This is a title</title>
          <meta content="text/html; charset=utf-8" http-equiv="content-type" />
        </head>
        <body>
          <div>
            <div>
              <p>This is a paragraph.</p>
              <p>Is this <a href="page2.html">a link</a>?</p>
              <br />
              Apparently.
            </div>
            <div class="second">
              Nothing to add.
              Except maybe this <a href="page3.html">other link</a>.
              <!-- And this comment -->
            </div>
          </div>
        </body>
        </html>



Order of predicates is important
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can have multiple predicates in sequence per step, each within its
``[]`` brackets, i.e. steps in the form of
``axis::nodetest[predicate#1][predicate#2][predicate#3]...``.

Predicates are processed in order, from left to right. And the output of
one predicate is fed into the next predicate filter, much like steps
produce node-sets for the next step to process.

So **the order of predicates is important.**

The following 2 location paths produce different results:

- ``//div[@class="second"][2]``: will output one ``<div>``
- ``//div[2][@class="second"]``: will select **nothing**

    .. xpathdemo:: //div[2][@class="second"]

        <html>
        <head>
          <title>This is a title</title>
          <meta content="text/html; charset=utf-8" http-equiv="content-type" />
        </head>
        <body>
          <div>
            <div>
              <p>This is a paragraph.</p>
              <p>Is this <a href="page2.html">a link</a>?</p>
              <br />
              Apparently.
            </div>
            <div class="second">
              Nothing to add.
              Except maybe this <a href="page3.html">other link</a>.
              <!-- And this comment -->
            </div>
          </div>
        </body>
        </html>

    .. xpathdemo:: //div[@class="second"][2]

        <html>
        <head>
          <title>This is a title</title>
          <meta content="text/html; charset=utf-8" http-equiv="content-type" />
        </head>
        <body>
          <div>
            <div>
              <p>This is a paragraph.</p>
              <p>Is this <a href="page2.html">a link</a>?</p>
              <br />
              Apparently.
            </div>
            <div class="second">
              Nothing to add.
              Except maybe this <a href="page3.html">other link</a>.
              <!-- And this comment -->
            </div>
          </div>
        </body>
        </html>


The second produces nothing indeed. Why is that?

``//div[2][@class="second"]`` looks at ``div`` elements that are the 2nd
child of their parent.
``div`` means ``child::div``, and ``[2]`` will select the 2nd node in the current node-set.
In our document this happens only once.
The final predicate, ``[@class="second"]``, filters nodes that have a
"class" attribute with value "second".
This happens to be valid for that 2nd child ``div``.

On the contrary, ``//div[@class="second"][2]`` will first produce
``//div[@class="second"]``, which only produces single-node node-sets
(again, there's only one ``div`` with "class" attribute with value
"second"). So the subsequent ``[2]`` predicate will never match with
single-node node-sets (you cannot select the 2nd element of a 1-element list)

Abbreviation cheatsheet
~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Abbreviated step
     - Meaning

   * - ``*`` (asterisk)
     - all **element** nodes (i.e. not text nodes, not attribute nodes).

       Remember that ``.//*`` is not the same as ``.//node()``.

       Also, there's no ``element()`` node test.

   * - ``@*``
     - ``attribute::*`` (all attribute nodes)

   * - ``//``
     - ``/descendant-or-self::node()/`` (exactly this, nothing more, nothing less)

       so ``//*`` is not the same as ``/descendant-or-self::*``

   * - ``.`` (a single dot)
     - ``self::node()``, the context node; useful for making XPaths relative,
       e.g. ``.//tr``

   * - ``..`` (2 dots)
     - ``parent::node()``

TODO: explain why ``//*`` is not the same as ``/descendant-or-self::*``

String functions
----------------

TODO

Part 3: Use-cases for web scraping
==================================

TODO

Text extraction
---------------

TODO

Attributes extraction
---------------------

TODO

Attribute names extractions
~~~~~~~~~~~~~~~~~~~~~~~~~~~

TODO

CSS Selectors
-------------

TODO

Loop on elements (table rows, lists)
------------------------------------

TODO

Element boundaries & XPath buckets (advanced)
---------------------------------------------

TODO

EXSLT extensions
----------------

TODO

Summary of tips
===============

.. tip::
    -  Use relative XPath expressions whenever possible
    -  Know your axes!
    -  Don't forget that XPath has ``string()`` and ``normalize-space()``
       functions
    -  **text() is a node test**, not a function call
    -  CSS selectors are very handy, easier to maintain, but also less
       powerful than XPath


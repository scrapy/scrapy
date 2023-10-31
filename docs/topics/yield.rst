.. _topics-yield:

==========================
'Yield' Keyword in Python and its use for Scrapy Callbacks
==========================
  
What is ``yield``?
====================
  
``Yield`` is a keyword in Python that returns a generator object. 

What is a 'generator'?
====================

A generator in Python is a function that returns an iterator. [#]_ It uses the ``yield`` keyword instead of ``return``.
If the body of a function contains ``yield``, the function automatically becomes a Python generator function. [#]_

In the following example, we have created a generator function that does nothing.

Example of a generator function: 

.. code-block:: python
  
  def NullGen(): 
    yield

How does ``yield`` work?
======================

The ``yield`` statement suspends a function’s execution and sends a value back to the caller, but retains enough state to enable
the function to resume where it left off. This allows its code to produce a series of values one by one, rather than computing
them all at once and sending them back like a list. [#]_ The key point to note here is that when the ``yield`` keyword is used to 
create a generator function, the values are *not* stored in memory as a list.

Example code:
-------------
  
.. code-block:: python

  # a simple generator function that returns values from 0 to 2
  def MyGen():
    yield 0
    yield 1
    yield 2
  
  # the values can be accesses using a loop
  for val in MyGen():
    print(val)
  
  # or we can create a new object as yield returns a generator object
  print("------------------------"
  temp = MyGen()
  
  # because temp is an iterable, we can use 'next' to access the values
  print(next(temp))
  print(next(temp))
  print(next(temp))

Explanation of sample code:
---------------------------

The first time the generator is called, it will run the code in the generator function from the beginning until the first ``yield``
is encountered and will return the first value. Subsequently, each call will run the generator function up to the next ``yield`` and
thus return the next value. This will continue until the last ``yield`` is hit.

More example code:
------------------

.. code-block:: python

  # a generator function with a loop
  def MyGen():
    for i in range (3):
      yield i
  # generator object
  temp = MyGen()
  for x in temp:
    print(x)

Explanation of sample code:
---------------------------

In the code snippet above, the first time the ``for`` calls the generator object created from the function ``MyGen()``, it will run the code
in ``MyGen()`` from the beginning until it hits ``yield`` and will return the first value of the loop. Subsequently, each call will run the 
next iteration of the loop written in the function ``MyGen()`` and the new value produced will be returned. This will continue until the
generator is considered empty, which happens when the function runs without hitting ``yield``.
Here, this happens because the loop inside ``MyGen()`` comes to an end. [#]_

``Yield`` v/s ``Return`` [#]_
=====================

..  csv-table:: 
    :header: "Return", "Yield"

    * sends a specified value back to its caller, * can produce a sequence of values
    * destroys the local variables’ states, * does not destroy the local variables’ states
    * function starts with a new set of variables every time it's called, * generator function will start right from where it left last

When to use ``yield``?
====================

We should use ``yield`` when we want to iterate over a sequence, but don’t want to store the entire sequence in memory. [#]_
Note that `yield` and `return` cannot be successfully used in combination in a single function. For example, the following code 
will only print values from 0 to 4. The value sent by `return` will not be included in the result.

.. code-block:: python

  def gen():
    for i in range(0,5):
        yield i
    print ("proof") # to show that we do actually reach this line and the one following it
    return 5
  res = gen()
  for x in res:
    print(x)

.. _topics-yield-scrapy:

Where is ``yield`` used in Scrapy?
==================================
``Yield`` is used for callbacks in Scrapy. For example, consider the following code
from :ref:`overview <intro-overview>` which walks through a simple spider that scrapes quotes from https://quotes.toscrape.com. 

.. code-block:: python

  import scrapy
  
  class QuotesSpider(scrapy.Spider):
      name = "quotes"
      start_urls = [
          "https://quotes.toscrape.com/tag/humor/",
      ]
  
      def parse(self, response):
          for quote in response.css("div.quote"):
              yield {
                  "author": quote.xpath("span/small/text()").get(),
                  "text": quote.css("span.text::text").get(),
              }
  
          next_page = response.css('li.next a::attr("href")').get()
          if next_page is not None:
              yield response.follow(next_page, self.parse)

The working of the code is adequately covered in :ref:`overview <intro-overview>`, so we will not go into the details
here. Now, let's address the question of the significance of using ``yield`` here.

Why ``yield``?
----------------
Scrapy is writtern with the Twisted Framework and thus, a core feature of Scrapy is that requests are scheduled and processed asynchronously
:ref:`topics-architecture`. As noted in :ref:`overview <intro-overview>`, this means that:
            | Scrapy doesn't need to wait for a request to be finished and processed, it can send another request or do other things in the meantime. 
            | This also means that other requests can keep going even if some request fails or an error happens while handling it.
This is where ``yield`` comes in. When we use ``yield`` for a Scrapy callback, we essentially pause the execution of the callback function at that 
point, allowing the framework to perform other tasks in a non-blocking manner. Later, the callback is resumed from where it was paused. Thus, using
yield ensures that the Scrapy framework can continue making requests and processing responses without blocking the event loop. 

Would ``return`` work?
----------------------
Technically, yes. If we wanted to use ``return``, we would have to wait until we had all data to ensure that nothing was missed because once the return
statement is encountered, the function execution will be ceased immediately and the function will be exited. Thus, using ``return`` could make the spider
inefficient, and may also lead to blocking behaviour and loss of Scrapy's asynchronous functionality. In general, using ``return`` may work in certain 
cases, but it is not recommended as it does not align with Scrapy's event-driven, non-blocking design.

Thus, in general, it is recommended to use ``yield``.

|
References/Resources:
---------------------

.. [#] A beginner's guide to iterators: https://www.w3schools.com/python/python_iterators.asp
.. [#] Reference: https://www.geeksforgeeks.org/generators-in-python/
.. [#] Reference: https://www.geeksforgeeks.org/use-yield-keyword-instead-return-keyword-python/
.. [#] Reference: https://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do-in-python
.. [#] Reference: https://www.simplilearn.com/tutorials/python-tutorial/yield-in-python
.. [#] Reference: https://www.geeksforgeeks.org/generators-in-python/

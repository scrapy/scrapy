.. _topics-yield:

==========================
'Yield' Keyword in Python
==========================
  
What is ``yield``?
====================
  
``Yield`` is a keyword in Python that returns a generator object. 

What is a *Generator*?
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

|
References/Resources:
---------------------

.. [#] A beginner's guide to iterators: https://www.w3schools.com/python/python_iterators.asp
.. [#] Reference: https://www.geeksforgeeks.org/generators-in-python/
.. [#] Reference: https://www.geeksforgeeks.org/use-yield-keyword-instead-return-keyword-python/
.. [#] Reference: https://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do-in-python
.. [#] Reference: https://www.simplilearn.com/tutorials/python-tutorial/yield-in-python
.. [#] Reference: https://www.geeksforgeeks.org/generators-in-python/

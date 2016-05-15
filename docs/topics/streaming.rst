.. _topic-streaming:

=========
Streaming
=========

The Scrapy Streaming provides an interface to write spiders using any programming language,
using json objects to make requests, parse web contents, get data, and more.

Also, we officially provide helper libraries to develop your spiders using Java, JS, and R.

External Spiders
================

We define ``External Spider`` as a spider developed in any programming language.

The external spider must communicate using the system ``stdin`` and ``stdout`` with the Streaming.

You can run standalone external spiders using the :command:`streaming` command.

If you want to integrate external spiders with a scrapy's project, create a file named ``external.json``
in your project root. This file must contain an array of json objects, each object with the ``name`` ,
``command``, and ``args`` attributes.

The ``name`` attribute will be used as documented in the :attr:`Spider.name <scrapy.spiders.Spider.name>`.
The ``command`` is the path or name of the executable to run your spider. The ``args`` attribute is
optional, this is an array with extra arguments to the command, if any.

For example, if you want to add spider developed in Java and a binary spider, you can define
the ``external.json`` as follows:

.. code-block:: python

    [
      {
        "name": "java_spider",
        "command": "java",
        "args": ["/home/user/MySpider"]
      },
      {
        "name": "compiled_spider",
        "command": "/home/user/my_executable"
      }
    ]


Communication Protocol
======================

The communication between the external spider and Scrapy Streaming will use json messages.

Every message must be escaped and ends with a line break ``\n``. Make sure to flush the stdout after
sending a message to avoid buffering.

After starting the spider, Scrapy will let it know that the communication chanel is ready sending
the :message:`ready` message.

Then, as the first message, the spider must send a :message:`spider` message with the necessary information.
The Scrapy Streaming will start the spider execution and return the :message:`response` with ``id`` equals to ``parse``.
Following this message, the external spider can sends any message listed bellow. To finish the spider execution, it must send the
the :message:`close` message.

The implementation of such procedure should contain a main loop, that checks the ``type`` of the data received
from Streaming, and then new actions can be done. It's recommended to always
check if the message if an :message:`exception` to avoid bugs in your implementation. Also, if the
Streaming finds anything wrong with the json message sent by the spider, a
:message:`error` message with the necessary information will be sent.

.. tip:: Every message contains a field named ``type``. You can use this field to easily identify
         the incoming data. The possible types are listed bellow.

Scrapy Streaming Messages:

* :message:`ready`
* :message:`response`
* :message:`response_selector`
* :message:`response_item_selector`
* :message:`exception`
* :message:`error`

External Spider Messages:

* :message:`spider`
* :message:`request`
* :message:`form_request`
* :message:`selector_request`
* :message:`item_selector_request`
* :message:`close`

.. note:: In this documentation, we use the ``*`` to identify that a field is optional.
          When implementing your spider, you can ommit this field and you must NOT use the ``*`` character
          in the field name as described here.

.. message:: ready

ready
-----
This message is sent by Streaming after starting and connecting with the process stdin/stdout.
This is a confirmation that communication channel is working.

.. code-block:: python

    {
        "type": "status",
        "status": "ready"
    }

.. message:: response

response
--------
Scrapy Streaming will serialize part of the :class:`~scrapy.http.Response` object.
See :class:`~scrapy.http.Response` for more information.

The response ``id`` will be the same that used in the :message:`request`. If it's the response from the initial spider
urls, the request ``id`` will be ``parse``.

.. code-block:: python

    {
        "type": "response",
        "id": string,
        "url": string,
        "headers": {},
        "status": int,
        "body": string,
        "meta": object,
        "flags": array
    }


.. message:: response_selector

response_selector
-----------------
This message will be sent by Streaming after receiving the response from a :message:`selector_request`.

It contains the fields as described in :message:`response`, plus an additional ``selector`` field
that is an array of strings with extracted data.

.. code-block:: python

    {
        "type": "response_selector",
        // ..., all response fields
        "selector": array of strings
    }

.. message:: response_item_selector

response_item_selector
----------------------
This message will be sent by Streaming after receiving the response from a :message:`item_selector_request`.

It contains the fields as described in :message:`response`, plus an additional ``item_selector`` field
that is an array of objects with extracted data. Each object consists of a field name (the key) and
its extracted value (string).

.. code-block:: python

    {
        "type": "response_selector",
        // ..., all response fields
        "item_selector": array of objects
    }

.. message:: exception

exception
---------
Exceptions are thrown when Scrapy faces a runtime error.

.. warning:: TODO. Add more details here. I need to implement to get more details about what can be an exception.

.. message:: error

error
-----
Errors are thrown if there is any problem with the validation of the received message. Runtime errors are thrown
by :message:`exception`.

If the Spider is using an unknown type, or an invalid field, for example, this message will be sent with the necessary information.

The Streaming will send the error details, and stops its execution.

The :message:`error` contains ``received_message`` field with the message received from external spider that
generated this error and ``details`` field, with a hint about what may be wrong with the spider.

.. code-block:: python

    {
        "type": "error",
        "received_message": string,
        "details": string
    }

.. message:: spider

spider
------
This is the firs message sent by your spider to Scrapy Streaming. It contains information about your Spider.
Read the :class:`~scrapy.spiders.Spider` docs for more information.

.. code-block:: python

    {
        "type": "spider",
        "name": string
        "start_urls": array
        *"allowed_domains": array
        *"custom_settings": object
    }


.. message:: request

request
-------
To open new requests in the running spider, use the request message. Read the :class:`~scrapy.http.Request` for more information.

The :message:`request` must contains the ``id`` field. Scrapy Streaming will send the response with this same ``id``,
so each response can be easily identified by its id.

.. code-block:: python

    {
        "type": "request",
        "id": string,
        "url": string,
        *"method": string,
        *"meta": object,
        *"body": string,
        *"headers": object,
        *"cookies": object or array of objects,
        *"encoding": string,
        *"priority": int,
        *"dont_filter": boolean
    }

.. message:: form_request

form_request
------------
The :message:`form_request` uses the :meth:`~scrapy.http.FormRequest.from_response` method.
Check the :class:`~scrapy.http.FormRequest` for more information.

It first creates a :class:`~scrapy.http.Request` and then use the response to create the :class:`~scrapy.http.FormRequest`

The type of this message is :message:`form_request`, it contains all fields described in :message:`request` doc,
and the :meth:`~scrapy.http.FormRequest.from_response` data in the ``form_request`` field.

You can define it as follows:

.. code-block:: python

    {
        "type": "form_request",

        ... // all request's fields here

        "form_request": {
            *"formname": string,
            *"formxpath": string,
            *"formcss": string,
            *"formnumber": string,
            *"formdata": object,
            *"clickdata": object,
            *"dont_click": boolean
        }
    }

The :message:`form_request` will return the response obtained from :class:`~scrapy.http.FormRequest` if
successful.

.. message:: selector_request

selector_request
----------------
The :message:`selector_request` can be used in order to extract data from the response. Read :ref:`topics-selectors` for more information.

The :message:`selector_request` message allows you to choose between css and xpath selectors.
It first creates a :class:`~scrapy.http.Request` and then parses the result with the desired selector.

The type of this message is :message:`selector_request`, it contains all fields described in :message:`request`,
and the ``selector`` object with the ``type`` and ``filter``. You can use it as follows:

.. code-block:: python

    {
        "type": "request",
        ... // all request's fields here

        "selector": {
            "type": "css" or "xpath",
            "filter": string
        }
    }

The :message:`selector_request` will return a list with the extracted data if successful.

.. message:: item_selector_request

item_selector_request
---------------------
The :message:`item_selector_request` can be used in order to extract items using multiple selectors.

It first creates a :class:`~scrapy.http.Request` and then parses the result with the desired selectors.

The type of this message is :message:`item_selector_request`, it contains all fields described in :message:`request`,
and the ``item_selector`` object with the item fields and its corresponding selectors.

.. code-block:: python

    {
        "type": "item_selector_request",
        ... // all request's fields here

        "item_selector": {
            "field 1": {
                "type": "css" or "xpath",
                "filter": string
            },
            "field 2": {
                "type": "css" or "xpath",
                "filter": string
            }

            ... // use field name: selector object
        }
    }

Each key of the ``item_selector`` object is the field name, and its value is a selector.

The :message:`item_selector_request` will return a list with the extracted items if successful. Each item will be
an object with its fields and extracted values.

.. message:: close

close
-----
To finish the spider execution, send the :message:`close` message. It'll stop any pending request, close the
communication channel, and stop the spider process.

The :message:`close` message contains only the ``type`` field, as follows:

.. code-block:: python

    {
        "type": "close"
    }


Sample Spider
-------------
TODO

Examples
========
TODO (add some spider implementations using the protocol above)

Helper Libraries
================

TODO

Java
----

TODO

R
-

TODO

Java Script
-----------

TODO
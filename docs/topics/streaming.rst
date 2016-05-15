.. _topic-streaming:

=========
Streaming
=========

The Scrapy Streaming provides an interface to write spiders using any programming language,
using json objects to make requests, parse web contents, get data, and more.

Also, we officially provide helper libraries to develop your spiders using Java, JS, and R.

External Spiders
================

We define ``External Spider`` a spider developed in any programming language.

The external spider must communicate using the system ``stdin`` and ``stdout`` with the Streaming.

You can run standalone external spiders using the :command:`streaming` command.

If you want to integrate external spiders with a scrapy's project, create a file named ``external.json``
in your project root. This file must contain an array of json objects, each object with the ``name`` ,
``command``, and ``args`` attributes.

The ``name`` attribute will be used as documented in the :ref:`topics-spiders-ref`.
The ``command`` is the path or name of the executable to run your spider. The ``args`` attribute is
optional, this is an array with extra arguments to the command, if any.

For example, if you want to add spider developed in Java and a binary spider, you can define
the ``external.json`` as follows::

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

The communication between your external spider and Scrapy Streaming will use json messages.

Every message must end with a line break ``\n``, and make sure to flush your process stdout after
sending every message to avoid buffering.

After starting your spider, Scrapy will let it know that the communication chanel is ready sending
the :message:`ready` message.

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
* :message:`selector`
* :message:`item_selector`
* :message:`close`

.. note:: In this documentation, we use the ``*`` to identify that a field is optional.
          When implementing your spider, you can ommit this field and you must NOT use the ``*`` character
          in the field name as described here.

.. note:: For readability, we present the json in multiline format. Notice the line break indicates the
          end of a message. Therefore, in your spider each message MUST be contained in a
          single line, and ends with the ``\n`` character.

.. message:: ready

ready
-----
This message is sent by Streaming after starting and connecting with the process stdin/stdout.
This is a confirmation that communication channel is working.
::

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
::

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
This message will be sent by Streaming after receiving the response from a :message:`selector`.

It contains the fields as described in :message:`response`, plus an additional ``selector`` field
that is an array of strings with extracted data.
::

    {
        "type": "response_selector",
        // ..., all response fields
        "selector": array of strings
    }

.. message:: response_item_selector

response_item_selector
----------------------
This message will be sent by Streaming after receiving the response from a :message:`item_selector`.

It contains the fields as described in :message:`response`, plus an additional ``item_selector`` field
that is an array of objects with extracted data. Each object consists of a field name (the key) and
its extracted value (string).

::

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


.. message:: spider

.. message:: error

error
-----
Errors are thrown if there is any problem with the validation of the received message. Runtime errors are thrown
by :message:`exception`.

If the Spider is using an unknown type, or an invalid field, for example, this message will be sent with the necessary information.

The Streaming will send the error details, and stops its execution.

The :message:`error` contains ``received_message`` field with the message received from external spider that
generated this error and ``details`` field, with a hint about what may be wrong with the spider.
::

    {
        "type": "error",
        "received_message": string,
        "details": string
    }


spider
------
This is the firs message sent by your spider to Scrapy Streaming. It contains information about your Spider.
::

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
To open new requests in the running spider, use the request message. This serializes part of
:class:`~scrapy.http.Request`. Read the :class:`~scrapy.http.Request` for more information.

The :message:`request` must contains the ``id`` field. Scrapy Streaming will send the response with this same ``id``,
so each response can be easily identified by its id.

::

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
        *"dont_filter": boolean,

        // special fields:
        *"form_request": see form_request documentation bellow,
        *"selector": see selector documentation bellow,
        *"item_selector": see item_selector documentation bellow
    }

.. note:: You can use only one of :message:`form_request`, :message:`selector`, and :message:`item_selector`
             per request. It's not allowed to use the :message:`form_request` and :message:`selector` at the
             same time, for example.

.. message:: form_request

form_request
------------
The :message:`form_request` serializes part of :meth:`~scrapy.http.FormRequest.from_response` method.
Check :class:`~scrapy.http.FormRequest` for more information.

It first creates a :class:`~scrapy.http.Request` and then use the response to create the :class:`~scrapy.http.FormRequest`

The type of this message is :message:`request`, it contains all fields described in :message:`request` doc,
and the :meth:`~scrapy.http.FormRequest.from_response` data in the ``form_request`` field.

You can define it as follows::

    {
        "type": "request",

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

.. message:: selector

selector
--------
The :message:`selector` can be used in order to extract data from the response. Read :ref:`topics-selectors` for more information.

The :message:`selector` message allows you to choose between css and xpath selectors.
It first creates a :class:`~scrapy.http.Request` and then parses the result with the desired selector.

The type of this message is :message:`request`, it contains all fields described in :message:`request` doc,
and the selector object with the ``selector`` and ``filter``. You can use it as follows::

    {
        "type": "request",
        ... // all request's fields here

        "selector": {
            "selector": "css" or "xpath",
            "filter": string
        }
    }

The :message:`selector` will return a list with the extracted data if successful.

.. message:: item_selector

item_selector
-------------
The :message:`item_selector` can be used in order to extract items using multiple :message:`selector` filters.

It first creates a :class:`~scrapy.http.Request` and then parses the result with the desired selectors.

The type of this message is :message:`request`, it contains all fields described in :message:`request` doc,
and the ``item_selector`` object with the item fields and its corresponding :message:`selectors <selector>`.
::

    {
        "type": "request",
        ... // all request's fields here

        "item_selector": {
            "field 1": object,
            "field 2": object
            ... // use field name: selector object
        }
    }

Each :message:`item_selector` key is the field name, and its value is a :message:`selector`.
The :message:`item_selector` will return a list with the extracted items if successful. Each item will be
an object with its fields and extracted values.

.. message:: close

close
-----
To finish the spider execution, send the :message:`close` message. It'll stop any pending request, close the
communication channel, and stop the spider process.

The :message:`close` message contains only the ``type`` field, as follows::

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
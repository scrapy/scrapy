.. _topics-contracts:

=================
Spiders Contracts
=================

.. versionadded:: 0.15

.. note:: This is a new feature (introduced in Scrapy 0.15) and may be subject
   to minor functionality/API updates. Check the :ref:`release notes <news>` to
   be notified of updates.

Testing spiders can get particularly annoying and while nothing prevents you
from writing unit tests the task gets cumbersome quickly. Scrapy offers an
integrated way of testing your spiders by the means of contracts.

This allows you to test each callback of your spider by hardcoding a sample url
and check various constraints for how the callback processes the response. Each
contract is prefixed with an ``@`` and included in the docstring. See the
following example::

    def parse(self, response):
        """ This function parses a sample response. Some contracts are mingled
        with this docstring.

        @url http://www.amazon.com/s?field-keywords=selfish+gene
        @returns items 1 16
        @returns requests 0 0
        @scrapes Title Author Year Price
        """

This callback is tested using three built-in contracts:

.. module:: scrapy.contracts.default

.. class:: UrlContract

    This contract (``@url``) sets the sample url used when checking other
    contract conditions for this spider. This contract is mandatory. All
    callbacks lacking this contract are ignored when running the checks::

    @url url

.. class:: ReturnsContract

    This contract (``@returns``) sets lower and upper bounds for the items and
    requests returned by the spider. The upper bound is optional::

    @returns item(s)|request(s) [min [max]]

.. class:: ScrapesContract

    This contract (``@scrapes``) checks that all the items returned by the
    callback have the specified fields::

    @scrapes field_1 field_2 ...

Use the :command:`check` command to run the contract checks.

Custom Contracts
================

If you find you need more power than the built-in scrapy contracts you can
create and load your own contracts in the project by using the
:setting:`SPIDER_CONTRACTS` setting::

    SPIDER_CONTRACTS = {
        'myproject.contracts.ResponseCheck': 10,
        'myproject.contracts.ItemValidate': 10,
    }

Each contract must inherit from :class:`scrapy.contracts.Contract` and can
override three methods:

.. module:: scrapy.contracts

.. class:: Contract(method, \*args)

    :param method: callback function to which the contract is associated
    :type method: function

    :param args: list of arguments passed into the docstring (whitespace
        separated)
    :type args: list

    .. method:: Contract.adjust_request_args(args)

        This receives a ``dict`` as an argument containing default arguments
        for :class:`~scrapy.http.Request` object. Must return the same or a
        modified version of it.

    .. method:: Contract.pre_process(response)

        This allows hooking in various checks on the response received from the
        sample request, before it's being passed to the callback.

    .. method:: Contract.post_process(output)

        This allows processing the output of the callback. Iterators are
        converted listified before being passed to this hook.

Here is a demo contract which checks the presence of a custom header in the
response received. Raise :class:`scrapy.exceptions.ContractFail` in order to
get the failures pretty printed::

    from scrapy.contracts import Contract
    from scrapy.exceptions import ContractFail

    class HasHeaderContract(Contract):
        """ Demo contract which checks the presence of a custom header
            @has_header X-CustomHeader
        """

        name = 'has_header'

        def pre_process(self, response):
            for header in self.args:
                if header not in response.headers:
                    raise ContractFail('X-CustomHeader not present')

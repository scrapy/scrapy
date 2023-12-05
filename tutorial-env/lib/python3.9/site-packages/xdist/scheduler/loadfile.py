from .loadscope import LoadScopeScheduling
from xdist.remote import Producer


class LoadFileScheduling(LoadScopeScheduling):
    """Implement load scheduling across nodes, but grouping test test file.

    This distributes the tests collected across all nodes so each test is run
    just once.  All nodes collect and submit the list of tests and when all
    collections are received it is verified they are identical collections.
    Then the collection gets divided up in work units, grouped by test file,
    and those work units get submitted to nodes.  Whenever a node finishes an
    item, it calls ``.mark_test_complete()`` which will trigger the scheduler
    to assign more work units if the number of pending tests for the node falls
    below a low-watermark.

    When created, ``numnodes`` defines how many nodes are expected to submit a
    collection. This is used to know when all nodes have finished collection.

    This class behaves very much like LoadScopeScheduling, but with a file-level scope.
    """

    def __init__(self, config, log=None):
        super().__init__(config, log)
        if log is None:
            self.log = Producer("loadfilesched")
        else:
            self.log = log.loadfilesched

    def _split_scope(self, nodeid):
        """Determine the scope (grouping) of a nodeid.

        There are usually 3 cases for a nodeid::

            example/loadsuite/test/test_beta.py::test_beta0
            example/loadsuite/test/test_delta.py::Delta1::test_delta0
            example/loadsuite/epsilon/__init__.py::epsilon.epsilon

        #. Function in a test module.
        #. Method of a class in a test module.
        #. Doctest in a function in a package.

        This function will group tests with the scope determined by splitting
        the first ``::`` from the left. That is, test will be grouped in a
        single work unit when they reside in the same file.
         In the above example, scopes will be::

            example/loadsuite/test/test_beta.py
            example/loadsuite/test/test_delta.py
            example/loadsuite/epsilon/__init__.py
        """
        return nodeid.split("::", 1)[0]

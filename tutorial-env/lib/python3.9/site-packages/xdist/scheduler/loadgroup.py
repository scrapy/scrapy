from .loadscope import LoadScopeScheduling
from xdist.remote import Producer


class LoadGroupScheduling(LoadScopeScheduling):
    """Implement load scheduling across nodes, but grouping test by xdist_group mark.

    This class behaves very much like LoadScopeScheduling, but it groups tests by xdist_group mark
    instead of the module or class to which they belong to.
    """

    def __init__(self, config, log=None):
        super().__init__(config, log)
        if log is None:
            self.log = Producer("loadgroupsched")
        else:
            self.log = log.loadgroupsched

    def _split_scope(self, nodeid):
        """Determine the scope (grouping) of a nodeid.

        There are usually 3 cases for a nodeid::

            example/loadsuite/test/test_beta.py::test_beta0
            example/loadsuite/test/test_delta.py::Delta1::test_delta0
            example/loadsuite/epsilon/__init__.py::epsilon.epsilon

        #. Function in a test module.
        #. Method of a class in a test module.
        #. Doctest in a function in a package.

        With loadgroup, two cases are added::

            example/loadsuite/test/test_beta.py::test_beta0
            example/loadsuite/test/test_delta.py::Delta1::test_delta0
            example/loadsuite/epsilon/__init__.py::epsilon.epsilon
            example/loadsuite/test/test_gamma.py::test_beta0@gname
            example/loadsuite/test/test_delta.py::Gamma1::test_gamma0@gname

        This function will group tests with the scope determined by splitting the first ``@``
        from the right. That is, test will be grouped in a single work unit when they have
        same group name. In the above example, scopes will be::

            example/loadsuite/test/test_beta.py::test_beta0
            example/loadsuite/test/test_delta.py::Delta1::test_delta0
            example/loadsuite/epsilon/__init__.py::epsilon.epsilon
            gname
            gname
        """
        if nodeid.rfind("@") > nodeid.rfind("]"):
            # check the index of ']' to avoid the case: parametrize mark value has '@'
            return nodeid.split("@")[-1]
        else:
            return nodeid

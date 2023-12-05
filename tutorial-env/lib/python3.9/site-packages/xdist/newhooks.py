"""
xdist hooks.

Additionally, pytest-xdist will also decorate a few other hooks
with the worker instance that executed the hook originally:

``pytest_runtest_logreport``: ``rep`` parameter has a ``node`` attribute.

You can use this hooks just as you would use normal pytest hooks, but some care
must be taken in plugins in case ``xdist`` is not installed. Please see:

    http://pytest.org/en/latest/writing_plugins.html#optionally-using-hooks-from-3rd-party-plugins
"""
import pytest


@pytest.hookspec()
def pytest_xdist_setupnodes(config, specs):
    """called before any remote node is set up."""


@pytest.hookspec()
def pytest_xdist_newgateway(gateway):
    """called on new raw gateway creation."""


@pytest.hookspec(
    warn_on_impl=DeprecationWarning(
        "rsync feature is deprecated and will be removed in pytest-xdist 4.0"
    )
)
def pytest_xdist_rsyncstart(source, gateways):
    """called before rsyncing a directory to remote gateways takes place."""


@pytest.hookspec(
    warn_on_impl=DeprecationWarning(
        "rsync feature is deprecated and will be removed in pytest-xdist 4.0"
    )
)
def pytest_xdist_rsyncfinish(source, gateways):
    """called after rsyncing a directory to remote gateways takes place."""


@pytest.hookspec(firstresult=True)
def pytest_xdist_getremotemodule():
    """called when creating remote node"""


@pytest.hookspec()
def pytest_configure_node(node):
    """configure node information before it gets instantiated."""


@pytest.hookspec()
def pytest_testnodeready(node):
    """Test Node is ready to operate."""


@pytest.hookspec()
def pytest_testnodedown(node, error):
    """Test Node is down."""


@pytest.hookspec()
def pytest_xdist_node_collection_finished(node, ids):
    """called by the controller node when a worker node finishes collecting."""


@pytest.hookspec(firstresult=True)
def pytest_xdist_make_scheduler(config, log):
    """return a node scheduler implementation"""


@pytest.hookspec(firstresult=True)
def pytest_xdist_auto_num_workers(config):
    """
    Return the number of workers to spawn when ``--numprocesses=auto`` is given in the
    command-line.

    .. versionadded:: 2.1
    """


@pytest.hookspec(firstresult=True)
def pytest_handlecrashitem(crashitem, report, sched):
    """
    Handle a crashitem, modifying the report if necessary.

    The scheduler is provided as a parameter to reschedule the test if desired with
    `sched.mark_test_pending`.

    def pytest_handlecrashitem(crashitem, report, sched):
        if should_rerun(crashitem):
            sched.mark_test_pending(crashitem)
            report.outcome = "rerun"

    .. versionadded:: 2.2.1
    """

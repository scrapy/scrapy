import os
import uuid
import sys
import warnings

import pytest


PYTEST_GTE_7 = hasattr(pytest, "version_tuple") and pytest.version_tuple >= (7, 0)  # type: ignore[attr-defined]

_sys_path = list(sys.path)  # freeze a copy of sys.path at interpreter startup


@pytest.hookimpl
def pytest_xdist_auto_num_workers(config):
    env_var = os.environ.get("PYTEST_XDIST_AUTO_NUM_WORKERS")
    if env_var:
        try:
            return int(env_var)
        except ValueError:
            warnings.warn(
                "PYTEST_XDIST_AUTO_NUM_WORKERS is not a number: {env_var!r}. Ignoring it."
            )

    try:
        import psutil
    except ImportError:
        pass
    else:
        use_logical = config.option.numprocesses == "logical"
        count = psutil.cpu_count(logical=use_logical) or psutil.cpu_count()
        if count:
            return count
    try:
        from os import sched_getaffinity

        def cpu_count():
            return len(sched_getaffinity(0))

    except ImportError:
        if os.environ.get("TRAVIS") == "true":
            # workaround https://bitbucket.org/pypy/pypy/issues/2375
            return 2
        try:
            from os import cpu_count
        except ImportError:
            from multiprocessing import cpu_count
    try:
        n = cpu_count()
    except NotImplementedError:
        return 1
    return n if n else 1


def parse_numprocesses(s):
    if s in ("auto", "logical"):
        return s
    elif s is not None:
        return int(s)


@pytest.hookimpl
def pytest_addoption(parser):
    group = parser.getgroup("xdist", "distributed and subprocess testing")
    group._addoption(
        "-n",
        "--numprocesses",
        dest="numprocesses",
        metavar="numprocesses",
        action="store",
        type=parse_numprocesses,
        help="Shortcut for '--dist=load --tx=NUM*popen'. With 'auto', attempt "
        "to detect physical CPU count. With 'logical', detect logical CPU "
        "count. If physical CPU count cannot be found, falls back to logical "
        "count. This will be 0 when used with --pdb.",
    )
    group.addoption(
        "--maxprocesses",
        dest="maxprocesses",
        metavar="maxprocesses",
        action="store",
        type=int,
        help="limit the maximum number of workers to process the tests when using --numprocesses=auto",
    )
    group.addoption(
        "--max-worker-restart",
        action="store",
        default=None,
        dest="maxworkerrestart",
        help="maximum number of workers that can be restarted "
        "when crashed (set to zero to disable this feature)",
    )
    group.addoption(
        "--dist",
        metavar="distmode",
        action="store",
        choices=[
            "each",
            "load",
            "loadscope",
            "loadfile",
            "loadgroup",
            "worksteal",
            "no",
        ],
        dest="dist",
        default="no",
        help=(
            "set mode for distributing tests to exec environments.\n\n"
            "each: send each test to all available environments.\n\n"
            "load: load balance by sending any pending test to any"
            " available environment.\n\n"
            "loadscope: load balance by sending pending groups of tests in"
            " the same scope to any available environment.\n\n"
            "loadfile: load balance by sending test grouped by file"
            " to any available environment.\n\n"
            "loadgroup: like load, but sends tests marked with 'xdist_group' to the same worker.\n\n"
            "worksteal: split the test suite between available environments,"
            " then rebalance when any worker runs out of tests.\n\n"
            "(default) no: run tests inprocess, don't distribute."
        ),
    )
    group.addoption(
        "--tx",
        dest="tx",
        action="append",
        default=[],
        metavar="xspec",
        help=(
            "add a test execution environment. some examples: "
            "--tx popen//python=python2.5 --tx socket=192.168.1.102:8888 "
            "--tx ssh=user@codespeak.net//chdir=testcache"
        ),
    )
    group._addoption(
        "-d",
        action="store_true",
        dest="distload",
        default=False,
        help="load-balance tests.  shortcut for '--dist=load'",
    )
    group.addoption(
        "--rsyncdir",
        action="append",
        default=[],
        metavar="DIR",
        help="add directory for rsyncing to remote tx nodes.",
    )
    group.addoption(
        "--rsyncignore",
        action="append",
        default=[],
        metavar="GLOB",
        help="add expression for ignores when rsyncing to remote tx nodes.",
    )
    group.addoption(
        "--testrunuid",
        action="store",
        help=(
            "provide an identifier shared amongst all workers as the value of "
            "the 'testrun_uid' fixture,\n\n,"
            "if not provided, 'testrun_uid' is filled with a new unique string "
            "on every test run."
        ),
    )
    group.addoption(
        "--maxschedchunk",
        action="store",
        type=int,
        help=(
            "Maximum number of tests scheduled in one step for --dist=load. "
            "Setting it to 1 will force pytest to send tests to workers one by "
            "one - might be useful for a small number of slow tests. "
            "Larger numbers will allow the scheduler to submit consecutive "
            "chunks of tests to workers - allows reusing fixtures. "
            "Due to implementation reasons, at least 2 tests are scheduled per "
            "worker at the start. Only later tests can be scheduled one by one. "
            "Unlimited if not set."
        ),
    )

    parser.addini(
        "rsyncdirs",
        "list of (relative) paths to be rsynced for remote distributed testing.",
        type="paths" if PYTEST_GTE_7 else "pathlist",
    )
    parser.addini(
        "rsyncignore",
        "list of (relative) glob-style paths to be ignored for rsyncing.",
        type="paths" if PYTEST_GTE_7 else "pathlist",
    )
    parser.addini(
        "looponfailroots",
        type="paths" if PYTEST_GTE_7 else "pathlist",
        help="directories to check for changes. Default: current directory.",
    )


# -------------------------------------------------------------------------
# distributed testing hooks
# -------------------------------------------------------------------------


@pytest.hookimpl
def pytest_addhooks(pluginmanager):
    from xdist import newhooks

    pluginmanager.add_hookspecs(newhooks)


# -------------------------------------------------------------------------
# distributed testing initialization
# -------------------------------------------------------------------------


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    config_line = (
        "xdist_group: specify group for tests should run in same session."
        "in relation to one another. Provided by pytest-xdist."
    )
    config.addinivalue_line("markers", config_line)

    # Skip this plugin entirely when only doing collection.
    if config.getvalue("collectonly"):
        return

    # Create the distributed session in case we have a valid distribution
    # mode and test environments.
    if config.getoption("dist") != "no" and config.getoption("tx"):
        from xdist.dsession import DSession

        session = DSession(config)
        config.pluginmanager.register(session, "dsession")
        tr = config.pluginmanager.getplugin("terminalreporter")
        if tr:
            tr.showfspath = False

    # Deprecation warnings for deprecated command-line/configuration options.
    if config.getoption("looponfail", None) or config.getini("looponfailroots"):
        warning = DeprecationWarning(
            "The --looponfail command line argument and looponfailroots config variable are deprecated.\n"
            "The loop-on-fail feature will be removed in pytest-xdist 4.0."
        )
        config.issue_config_time_warning(warning, 2)

    if config.getoption("rsyncdir", None) or config.getini("rsyncdirs"):
        warning = DeprecationWarning(
            "The --rsyncdir command line argument and rsyncdirs config variable are deprecated.\n"
            "The rsync feature will be removed in pytest-xdist 4.0."
        )
        config.issue_config_time_warning(warning, 2)


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config):
    usepdb = config.getoption("usepdb", False)  # a core option
    if config.option.numprocesses in ("auto", "logical"):
        if usepdb:
            config.option.numprocesses = 0
            config.option.dist = "no"
        else:
            auto_num_cpus = config.hook.pytest_xdist_auto_num_workers(config=config)
            config.option.numprocesses = auto_num_cpus

    if config.option.numprocesses:
        if config.option.dist == "no":
            config.option.dist = "load"
        numprocesses = config.option.numprocesses
        if config.option.maxprocesses:
            numprocesses = min(numprocesses, config.option.maxprocesses)
        config.option.tx = ["popen"] * numprocesses
    if config.option.distload:
        config.option.dist = "load"
    val = config.getvalue
    if not val("collectonly") and val("dist") != "no" and usepdb:
        raise pytest.UsageError(
            "--pdb is incompatible with distributing tests; try using -n0 or -nauto."
        )  # noqa: E501


# -------------------------------------------------------------------------
# fixtures and API to easily know the role of current node
# -------------------------------------------------------------------------


def is_xdist_worker(request_or_session) -> bool:
    """Return `True` if this is an xdist worker, `False` otherwise

    :param request_or_session: the `pytest` `request` or `session` object
    """
    return hasattr(request_or_session.config, "workerinput")


def is_xdist_controller(request_or_session) -> bool:
    """Return `True` if this is the xdist controller, `False` otherwise

    Note: this method also returns `False` when distribution has not been
    activated at all.

    :param request_or_session: the `pytest` `request` or `session` object
    """
    return (
        not is_xdist_worker(request_or_session)
        and request_or_session.config.option.dist != "no"
    )


# ALIAS: TODO, deprecate (#592)
is_xdist_master = is_xdist_controller


def get_xdist_worker_id(request_or_session):
    """Return the id of the current worker ('gw0', 'gw1', etc) or 'master'
    if running on the controller node.

    If not distributing tests (for example passing `-n0` or not passing `-n` at all)
    also return 'master'.

    :param request_or_session: the `pytest` `request` or `session` object
    """
    if hasattr(request_or_session.config, "workerinput"):
        return request_or_session.config.workerinput["workerid"]
    else:
        # TODO: remove "master", ideally for a None
        return "master"


@pytest.fixture(scope="session")
def worker_id(request):
    """Return the id of the current worker ('gw0', 'gw1', etc) or 'master'
    if running on the master node.
    """
    # TODO: remove "master", ideally for a None
    return get_xdist_worker_id(request)


@pytest.fixture(scope="session")
def testrun_uid(request):
    """Return the unique id of the current test."""
    if hasattr(request.config, "workerinput"):
        return request.config.workerinput["testrunuid"]
    else:
        return uuid.uuid4().hex

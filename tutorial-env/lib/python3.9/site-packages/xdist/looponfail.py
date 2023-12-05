"""
    Implement -f aka looponfailing for pytest.

    NOTE that we try to avoid loading and depending on application modules
    within the controlling process (the one that starts repeatedly test
    processes) otherwise changes to source code can crash
    the controlling process which should best never happen.
"""
import os
from pathlib import Path
from typing import Dict, Sequence

import pytest
import sys
import time
import execnet
from _pytest._io import TerminalWriter

from xdist._path import visit_path


@pytest.hookimpl
def pytest_addoption(parser):
    group = parser.getgroup("xdist", "distributed and subprocess testing")
    group._addoption(
        "-f",
        "--looponfail",
        action="store_true",
        dest="looponfail",
        default=False,
        help="run tests in subprocess, wait for modified files "
        "and re-run failing test set until all pass.",
    )


@pytest.hookimpl
def pytest_cmdline_main(config):
    if config.getoption("looponfail"):
        usepdb = config.getoption("usepdb", False)  # a core option
        if usepdb:
            raise pytest.UsageError("--pdb is incompatible with --looponfail.")
        looponfail_main(config)
        return 2  # looponfail only can get stop with ctrl-C anyway


def looponfail_main(config: "pytest.Config") -> None:
    remotecontrol = RemoteControl(config)
    config_roots = config.getini("looponfailroots")
    if not config_roots:
        config_roots = [Path.cwd()]
    rootdirs = [Path(root) for root in config_roots]
    statrecorder = StatRecorder(rootdirs)
    try:
        while 1:
            remotecontrol.loop_once()
            if not remotecontrol.failures and remotecontrol.wasfailing:
                # the last failures passed, let's immediately rerun all
                continue
            repr_pytest_looponfailinfo(
                failreports=remotecontrol.failures, rootdirs=rootdirs
            )
            statrecorder.waitonchange(checkinterval=2.0)
    except KeyboardInterrupt:
        print()


class RemoteControl:
    def __init__(self, config):
        self.config = config
        self.failures = []

    def trace(self, *args):
        if self.config.option.debug:
            msg = " ".join(str(x) for x in args)
            print("RemoteControl:", msg)

    def initgateway(self):
        return execnet.makegateway("popen")

    def setup(self, out=None):
        if out is None:
            out = TerminalWriter()
        if hasattr(self, "gateway"):
            raise ValueError("already have gateway %r" % self.gateway)
        self.trace("setting up worker session")
        self.gateway = self.initgateway()
        self.channel = channel = self.gateway.remote_exec(
            init_worker_session,
            args=self.config.args,
            option_dict=vars(self.config.option),
        )
        remote_outchannel = channel.receive()

        def write(s):
            out._file.write(s)
            out._file.flush()

        remote_outchannel.setcallback(write)

    def ensure_teardown(self):
        if hasattr(self, "channel"):
            if not self.channel.isclosed():
                self.trace("closing", self.channel)
                self.channel.close()
            del self.channel
        if hasattr(self, "gateway"):
            self.trace("exiting", self.gateway)
            self.gateway.exit()
            del self.gateway

    def runsession(self):
        try:
            self.trace("sending", self.failures)
            self.channel.send(self.failures)
            try:
                return self.channel.receive()
            except self.channel.RemoteError:
                e = sys.exc_info()[1]
                self.trace("ERROR", e)
                raise
        finally:
            self.ensure_teardown()

    def loop_once(self):
        self.setup()
        self.wasfailing = self.failures and len(self.failures)
        result = self.runsession()
        failures, reports, collection_failed = result
        if collection_failed:
            pass  # "Collection failed, keeping previous failure set"
        else:
            uniq_failures = []
            for failure in failures:
                if failure not in uniq_failures:
                    uniq_failures.append(failure)
            self.failures = uniq_failures


def repr_pytest_looponfailinfo(failreports, rootdirs):
    tr = TerminalWriter()
    if failreports:
        tr.sep("#", "LOOPONFAILING", bold=True)
        for report in failreports:
            if report:
                tr.line(report, red=True)
    tr.sep("#", "waiting for changes", bold=True)
    for rootdir in rootdirs:
        tr.line(f"### Watching:   {rootdir}", bold=True)


def init_worker_session(channel, args, option_dict):
    import os
    import sys

    outchannel = channel.gateway.newchannel()
    sys.stdout = sys.stderr = outchannel.makefile("w")
    channel.send(outchannel)
    # prune sys.path to not contain relative paths
    newpaths = []
    for p in sys.path:
        if p:
            if not os.path.isabs(p):
                p = os.path.abspath(p)
            newpaths.append(p)
    sys.path[:] = newpaths

    # fullwidth, hasmarkup = channel.receive()
    from _pytest.config import Config

    config = Config.fromdictargs(option_dict, list(args))
    config.args = args
    from xdist.looponfail import WorkerFailSession

    WorkerFailSession(config, channel).main()


class WorkerFailSession:
    def __init__(self, config, channel):
        self.config = config
        self.channel = channel
        self.recorded_failures = []
        self.collection_failed = False
        config.pluginmanager.register(self)
        config.option.looponfail = False
        config.option.usepdb = False

    def DEBUG(self, *args):
        if self.config.option.debug:
            print(" ".join(map(str, args)))

    @pytest.hookimpl
    def pytest_collection(self, session):
        self.session = session
        self.trails = self.current_command
        hook = self.session.ihook
        try:
            items = session.perform_collect(self.trails or None)
        except pytest.UsageError:
            items = session.perform_collect(None)
        hook.pytest_collection_modifyitems(
            session=session, config=session.config, items=items
        )
        hook.pytest_collection_finish(session=session)
        return True

    @pytest.hookimpl
    def pytest_runtest_logreport(self, report):
        if report.failed:
            self.recorded_failures.append(report)

    @pytest.hookimpl
    def pytest_collectreport(self, report):
        if report.failed:
            self.recorded_failures.append(report)
            self.collection_failed = True

    def main(self):
        self.DEBUG("WORKER: received configuration, waiting for command trails")
        try:
            command = self.channel.receive()
        except KeyboardInterrupt:
            return  # in the worker we can't do much about this
        self.DEBUG("received", command)
        self.current_command = command
        self.config.hook.pytest_cmdline_main(config=self.config)
        trails, failreports = [], []
        for rep in self.recorded_failures:
            trails.append(rep.nodeid)
            loc = rep.longrepr
            loc = str(getattr(loc, "reprcrash", loc))
            failreports.append(loc)
        self.channel.send((trails, failreports, self.collection_failed))


class StatRecorder:
    def __init__(self, rootdirlist: Sequence[Path]) -> None:
        self.rootdirlist = rootdirlist
        self.statcache: Dict[Path, os.stat_result] = {}
        self.check()  # snapshot state

    def fil(self, p: Path) -> bool:
        return p.is_file() and not p.name.startswith(".") and p.suffix != ".pyc"

    def rec(self, p: Path) -> bool:
        return not p.name.startswith(".") and p.exists()

    def waitonchange(self, checkinterval=1.0):
        while 1:
            changed = self.check()
            if changed:
                return
            time.sleep(checkinterval)

    def check(self, removepycfiles: bool = True) -> bool:  # noqa, too complex
        changed = False
        newstat: Dict[Path, os.stat_result] = {}
        for rootdir in self.rootdirlist:
            for path in visit_path(rootdir, filter=self.fil, recurse=self.rec):
                oldstat = self.statcache.pop(path, None)
                try:
                    curstat = path.stat()
                except OSError:
                    if oldstat:
                        changed = True
                else:
                    newstat[path] = curstat
                    if oldstat is not None:
                        if (
                            oldstat.st_mtime != curstat.st_mtime
                            or oldstat.st_size != curstat.st_size
                        ):
                            changed = True
                            print("# MODIFIED", path)
                            if removepycfiles and path.suffix == ".py":
                                pycfile = path.with_suffix(".pyc")
                                if pycfile.is_file():
                                    os.unlink(pycfile)

                    else:
                        changed = True
        if self.statcache:
            changed = True
        self.statcache = newstat
        return changed

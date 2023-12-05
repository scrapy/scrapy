import fnmatch
import os
import re
import sys
import uuid
from pathlib import Path
from typing import List, Union, Sequence, Optional, Any, Tuple, Set

import pytest
import execnet

import xdist.remote
from xdist.remote import Producer
from xdist.plugin import _sys_path


def parse_spec_config(config):
    xspeclist = []
    for xspec in config.getvalue("tx"):
        i = xspec.find("*")
        try:
            num = int(xspec[:i])
        except ValueError:
            xspeclist.append(xspec)
        else:
            xspeclist.extend([xspec[i + 1 :]] * num)
    if not xspeclist:
        raise pytest.UsageError(
            "MISSING test execution (tx) nodes: please specify --tx"
        )
    return xspeclist


class NodeManager:
    EXIT_TIMEOUT = 10
    DEFAULT_IGNORES = [".*", "*.pyc", "*.pyo", "*~"]

    def __init__(self, config, specs=None, defaultchdir="pyexecnetcache") -> None:
        self.config = config
        self.trace = self.config.trace.get("nodemanager")
        self.testrunuid = self.config.getoption("testrunuid")
        if self.testrunuid is None:
            self.testrunuid = uuid.uuid4().hex
        self.group = execnet.Group()
        if specs is None:
            specs = self._getxspecs()
        self.specs = []
        for spec in specs:
            if not isinstance(spec, execnet.XSpec):
                spec = execnet.XSpec(spec)
            if not spec.chdir and not spec.popen:
                spec.chdir = defaultchdir
            self.group.allocate_id(spec)
            self.specs.append(spec)
        self.roots = self._getrsyncdirs()
        self.rsyncoptions = self._getrsyncoptions()
        self._rsynced_specs: Set[Tuple[Any, Any]] = set()

    def rsync_roots(self, gateway):
        """Rsync the set of roots to the node's gateway cwd."""
        if self.roots:
            for root in self.roots:
                self.rsync(gateway, root, **self.rsyncoptions)

    def setup_nodes(self, putevent):
        self.config.hook.pytest_xdist_setupnodes(config=self.config, specs=self.specs)
        self.trace("setting up nodes")
        return [self.setup_node(spec, putevent) for spec in self.specs]

    def setup_node(self, spec, putevent):
        gw = self.group.makegateway(spec)
        self.config.hook.pytest_xdist_newgateway(gateway=gw)
        self.rsync_roots(gw)
        node = WorkerController(self, gw, self.config, putevent)
        gw.node = node  # keep the node alive
        node.setup()
        self.trace("started node %r" % node)
        return node

    def teardown_nodes(self):
        self.group.terminate(self.EXIT_TIMEOUT)

    def _getxspecs(self):
        return [execnet.XSpec(x) for x in parse_spec_config(self.config)]

    def _getrsyncdirs(self) -> List[Path]:
        for spec in self.specs:
            if not spec.popen or spec.chdir:
                break
        else:
            return []
        import pytest
        import _pytest

        def get_dir(p):
            """Return the directory path if p is a package or the path to the .py file otherwise."""
            stripped = p.rstrip("co")
            if os.path.basename(stripped) == "__init__.py":
                return os.path.dirname(p)
            else:
                return stripped

        pytestpath = get_dir(pytest.__file__)
        pytestdir = get_dir(_pytest.__file__)
        config = self.config
        candidates = [pytestpath, pytestdir]
        candidates += config.option.rsyncdir
        rsyncroots = config.getini("rsyncdirs")
        if rsyncroots:
            candidates.extend(rsyncroots)
        roots = []
        for root in candidates:
            root = Path(root).resolve()
            if not root.exists():
                raise pytest.UsageError(f"rsyncdir doesn't exist: {root!r}")
            if root not in roots:
                roots.append(root)
        return roots

    def _getrsyncoptions(self):
        """Get options to be passed for rsync."""
        ignores = list(self.DEFAULT_IGNORES)
        ignores += [str(path) for path in self.config.option.rsyncignore]
        ignores += [str(path) for path in self.config.getini("rsyncignore")]

        return {
            "ignores": ignores,
            "verbose": getattr(self.config.option, "verbose", 0),
        }

    def rsync(self, gateway, source, notify=None, verbose=False, ignores=None):
        """Perform rsync to remote hosts for node."""
        # XXX This changes the calling behaviour of
        #     pytest_xdist_rsyncstart and pytest_xdist_rsyncfinish to
        #     be called once per rsync target.
        rsync = HostRSync(source, verbose=verbose, ignores=ignores)
        spec = gateway.spec
        if spec.popen and not spec.chdir:
            # XXX This assumes that sources are python-packages
            #     and that adding the basedir does not hurt.
            gateway.remote_exec(
                """
                import sys ; sys.path.insert(0, %r)
            """
                % os.path.dirname(str(source))
            ).waitclose()
            return
        if (spec, source) in self._rsynced_specs:
            return

        def finished():
            if notify:
                notify("rsyncrootready", spec, source)

        rsync.add_target_host(gateway, finished=finished)
        self._rsynced_specs.add((spec, source))
        self.config.hook.pytest_xdist_rsyncstart(source=source, gateways=[gateway])
        rsync.send()
        self.config.hook.pytest_xdist_rsyncfinish(source=source, gateways=[gateway])


class HostRSync(execnet.RSync):
    """RSyncer that filters out common files"""

    PathLike = Union[str, "os.PathLike[str]"]

    def __init__(
        self,
        sourcedir: PathLike,
        *,
        ignores: Optional[Sequence[PathLike]] = None,
        **kwargs: object
    ) -> None:
        if ignores is None:
            ignores = []
        self._ignores = [re.compile(fnmatch.translate(os.fspath(x))) for x in ignores]
        super().__init__(sourcedir=Path(sourcedir), **kwargs)

    def filter(self, path: PathLike) -> bool:
        path = Path(path)
        for cre in self._ignores:
            if cre.match(path.name) or cre.match(str(path)):
                return False
        else:
            return True

    def add_target_host(self, gateway, finished=None):
        remotepath = os.path.basename(self._sourcedir)
        super().add_target(gateway, remotepath, finishedcallback=finished, delete=True)

    def _report_send_file(self, gateway, modified_rel_path):
        if self._verbose > 0:
            path = os.path.basename(self._sourcedir) + "/" + modified_rel_path
            remotepath = gateway.spec.chdir
            print(f"{gateway.spec}:{remotepath} <= {path}")


def make_reltoroot(roots: Sequence[Path], args: List[str]) -> List[str]:
    # XXX introduce/use public API for splitting pytest args
    splitcode = "::"
    result = []
    for arg in args:
        parts = arg.split(splitcode)
        fspath = Path(parts[0])
        try:
            exists = fspath.exists()
        except OSError:
            exists = False
        if not exists:
            result.append(arg)
            continue
        for root in roots:
            x: Optional[Path]
            try:
                x = fspath.relative_to(root)
            except ValueError:
                x = None
            if x or fspath == root:
                parts[0] = root.name + "/" + str(x)
                break
        else:
            raise ValueError(f"arg {arg} not relative to an rsync root")
        result.append(splitcode.join(parts))
    return result


class WorkerController:
    ENDMARK = -1

    class RemoteHook:
        @pytest.hookimpl(trylast=True)
        def pytest_xdist_getremotemodule(self):
            return xdist.remote

    def __init__(self, nodemanager, gateway, config, putevent):
        config.pluginmanager.register(self.RemoteHook())
        self.nodemanager = nodemanager
        self.putevent = putevent
        self.gateway = gateway
        self.config = config
        self.workerinput = {
            "workerid": gateway.id,
            "workercount": len(nodemanager.specs),
            "testrunuid": nodemanager.testrunuid,
            "mainargv": sys.argv,
        }
        self._down = False
        self._shutdown_sent = False
        self.log = Producer(f"workerctl-{gateway.id}", enabled=config.option.debug)

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.gateway.id}>"

    @property
    def shutting_down(self):
        return self._down or self._shutdown_sent

    def setup(self):
        self.log("setting up worker session")
        spec = self.gateway.spec
        if hasattr(self.config, "invocation_params"):
            args = [str(x) for x in self.config.invocation_params.args or ()]
            option_dict = {}
        else:
            args = self.config.args
            option_dict = vars(self.config.option)
        if not spec.popen or spec.chdir:
            args = make_reltoroot(self.nodemanager.roots, args)
        if spec.popen:
            name = "popen-%s" % self.gateway.id
            if hasattr(self.config, "_tmp_path_factory"):
                basetemp = self.config._tmp_path_factory.getbasetemp()
                option_dict["basetemp"] = str(basetemp / name)
        self.config.hook.pytest_configure_node(node=self)

        remote_module = self.config.hook.pytest_xdist_getremotemodule()
        self.channel = self.gateway.remote_exec(remote_module)
        # change sys.path only for remote workers
        # restore sys.path from a frozen copy for local workers
        change_sys_path = _sys_path if self.gateway.spec.popen else None
        self.channel.send((self.workerinput, args, option_dict, change_sys_path))

        if self.putevent:
            self.channel.setcallback(self.process_from_remote, endmarker=self.ENDMARK)

    def ensure_teardown(self):
        if hasattr(self, "channel"):
            if not self.channel.isclosed():
                self.log("closing", self.channel)
                self.channel.close()
            # del self.channel
        if hasattr(self, "gateway"):
            self.log("exiting", self.gateway)
            self.gateway.exit()
            # del self.gateway

    def send_runtest_some(self, indices):
        self.sendcommand("runtests", indices=indices)

    def send_runtest_all(self):
        self.sendcommand("runtests_all")

    def send_steal(self, indices):
        self.sendcommand("steal", indices=indices)

    def shutdown(self):
        if not self._down:
            try:
                self.sendcommand("shutdown")
            except OSError:
                pass
            self._shutdown_sent = True

    def sendcommand(self, name, **kwargs):
        """send a named parametrized command to the other side."""
        self.log(f"sending command {name}(**{kwargs})")
        self.channel.send((name, kwargs))

    def notify_inproc(self, eventname, **kwargs):
        self.log(f"queuing {eventname}(**{kwargs})")
        self.putevent((eventname, kwargs))

    def process_from_remote(self, eventcall):  # noqa too complex
        """this gets called for each object we receive from
        the other side and if the channel closes.

        Note that channel callbacks run in the receiver
        thread of execnet gateways - we need to
        avoid raising exceptions or doing heavy work.
        """
        try:
            if eventcall == self.ENDMARK:
                err = self.channel._getremoteerror()
                if not self._down:
                    if not err or isinstance(err, EOFError):
                        err = "Not properly terminated"  # lost connection?
                    self.notify_inproc("errordown", node=self, error=err)
                    self._down = True
                return
            eventname, kwargs = eventcall
            if eventname in ("collectionstart",):
                self.log(f"ignoring {eventname}({kwargs})")
            elif eventname == "workerready":
                self.notify_inproc(eventname, node=self, **kwargs)
            elif eventname == "internal_error":
                self.notify_inproc(eventname, node=self, **kwargs)
            elif eventname == "workerfinished":
                self._down = True
                self.workeroutput = kwargs["workeroutput"]
                self.notify_inproc("workerfinished", node=self)
            elif eventname in ("logstart", "logfinish"):
                self.notify_inproc(eventname, node=self, **kwargs)
            elif eventname in ("testreport", "collectreport", "teardownreport"):
                item_index = kwargs.pop("item_index", None)
                rep = self.config.hook.pytest_report_from_serializable(
                    config=self.config, data=kwargs["data"]
                )
                if item_index is not None:
                    rep.item_index = item_index
                self.notify_inproc(eventname, node=self, rep=rep)
            elif eventname == "collectionfinish":
                self.notify_inproc(eventname, node=self, ids=kwargs["ids"])
            elif eventname == "runtest_protocol_complete":
                self.notify_inproc(eventname, node=self, **kwargs)
            elif eventname == "unscheduled":
                self.notify_inproc(eventname, node=self, **kwargs)
            elif eventname == "logwarning":
                self.notify_inproc(
                    eventname,
                    message=kwargs["message"],
                    code=kwargs["code"],
                    nodeid=kwargs["nodeid"],
                    fslocation=kwargs["nodeid"],
                )
            elif eventname == "warning_captured":
                warning_message = unserialize_warning_message(
                    kwargs["warning_message_data"]
                )
                self.notify_inproc(
                    eventname,
                    warning_message=warning_message,
                    when=kwargs["when"],
                    item=kwargs["item"],
                )
            elif eventname == "warning_recorded":
                warning_message = unserialize_warning_message(
                    kwargs["warning_message_data"]
                )
                self.notify_inproc(
                    eventname,
                    warning_message=warning_message,
                    when=kwargs["when"],
                    nodeid=kwargs["nodeid"],
                    location=kwargs["location"],
                )
            else:
                raise ValueError(f"unknown event: {eventname}")
        except KeyboardInterrupt:
            # should not land in receiver-thread
            raise
        except:  # noqa
            from _pytest._code import ExceptionInfo

            excinfo = ExceptionInfo.from_current()
            print("!" * 20, excinfo)
            self.config.notify_exception(excinfo)
            self.shutdown()
            self.notify_inproc("errordown", node=self, error=excinfo)


def unserialize_warning_message(data):
    import warnings
    import importlib

    if data["message_module"]:
        mod = importlib.import_module(data["message_module"])
        cls = getattr(mod, data["message_class_name"])
        message = None
        if data["message_args"] is not None:
            try:
                message = cls(*data["message_args"])
            except TypeError:
                pass
        if message is None:
            # could not recreate the original warning instance;
            # create a generic Warning instance with the original
            # message at least
            message_text = "{mod}.{cls}: {msg}".format(
                mod=data["message_module"],
                cls=data["message_class_name"],
                msg=data["message_str"],
            )
            message = Warning(message_text)
    else:
        message = data["message_str"]

    if data["category_module"]:
        mod = importlib.import_module(data["category_module"])
        category = getattr(mod, data["category_class_name"])
    else:
        category = None

    kwargs = {"message": message, "category": category}
    # access private _WARNING_DETAILS because the attributes vary between Python versions
    for attr_name in warnings.WarningMessage._WARNING_DETAILS:  # type: ignore[attr-defined]
        if attr_name in ("message", "category"):
            continue
        kwargs[attr_name] = data[attr_name]

    return warnings.WarningMessage(**kwargs)  # type: ignore[arg-type]

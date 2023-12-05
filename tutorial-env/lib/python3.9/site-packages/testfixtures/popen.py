import shlex
from functools import wraps, partial, reduce
from io import TextIOWrapper
from itertools import chain, zip_longest
from os import PathLike
from subprocess import STDOUT, PIPE
from tempfile import TemporaryFile
from testfixtures.utils import extend_docstring
from typing import Union, Callable, List, Optional, Sequence, Tuple, Dict, Iterable
from .mock import Mock, call, _Call as Call


AnyStr = Union[str, bytes]
Command = Union[str, PathLike, Sequence[str]]


def shell_join(command: Command) -> str:
    if isinstance(command, str):
        return command
    elif isinstance(command, PathLike):
        return str(command)
    elif isinstance(command, Iterable):
        quoted_parts = []
        for part in command:
            if isinstance(part, PathLike):
                part = str(part)
            elif not isinstance(part, str):
                raise TypeError(f'{part!r} in {command} was {type(part)}, must be str')
            quoted_parts.append(shlex.quote(part))
        return " ".join(quoted_parts)
    else:
        raise TypeError(f'{command!r} was {type(command)}, must be str')


class PopenBehaviour(object):
    """
    An object representing the behaviour of a :class:`MockPopen` when
    simulating a particular command.
    """

    def __init__(
            self,
            stdout: bytes = b'',
            stderr: bytes = b'',
            returncode: int = 0,
            pid: int = 1234,
            poll_count: int = 3
    ):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.pid = pid
        self.poll_count = poll_count


def record(func) -> Callable:
    @wraps(func)
    def recorder(self, *args, **kw):
        self._record((func.__name__,), *args, **kw)
        return func(self, *args, **kw)
    return recorder


class MockPopenInstance(object):
    """
    A mock process as returned by :class:`MockPopen`.
    """

    #: A :class:`~unittest.mock.Mock` representing the pipe into this process.
    #: This is only set if ``stdin=PIPE`` is passed the constructor.
    #: The mock records writes and closes in :attr:`MockPopen.all_calls`.
    stdin: Mock = None

    #: A file representing standard output from this process.
    stdout: TemporaryFile = None

    #: A file representing error output from this process.
    stderr: TemporaryFile = None

    # These are not types as instantiation of this class is an internal implementation detail.
    def __init__(self, mock_class, root_call,
                 args, bufsize=0, executable=None,
                 stdin=None, stdout=None, stderr=None,
                 preexec_fn=None, close_fds=False, shell=False, cwd=None,
                 env=None, universal_newlines=False,
                 startupinfo=None, creationflags=0, restore_signals=True,
                 start_new_session=False, pass_fds=(),
                 encoding=None, errors=None, text=None):
        self.mock: Mock = Mock()
        self.class_instance_mock: Mock = mock_class.mock.Popen_instance
        #: A :func:`unittest.mock.call` representing the call made to instantiate
        #: this mock process.
        self.root_call: Call = root_call
        #: The calls made on this mock process, represented using
        #: :func:`~unittest.mock.call` instances.
        self.calls: List[Call] = []
        self.all_calls: List[Call] = mock_class.all_calls

        cmd = shell_join(args)

        behaviour = mock_class.commands.get(cmd, mock_class.default_behaviour)
        if behaviour is None:
            raise KeyError('Nothing specified for command %r' % cmd)

        if callable(behaviour):
            behaviour = behaviour(command=cmd, stdin=stdin)

        self.behaviour: PopenBehaviour = behaviour

        stdout_value = behaviour.stdout
        stderr_value = behaviour.stderr

        if stderr == STDOUT:
            line_iterator = chain.from_iterable(zip_longest(
                stdout_value.splitlines(True),
                stderr_value.splitlines(True)
            ))
            stdout_value = b''.join(l for l in line_iterator if l)
            stderr_value = None

        self.poll_count: int = behaviour.poll_count
        for name, option, mock_value in (
            ('stdout', stdout, stdout_value),
            ('stderr', stderr, stderr_value)
        ):
            value = None
            if option is PIPE:
                value = TemporaryFile()
                value.write(mock_value)
                value.flush()
                value.seek(0)
                if universal_newlines or text or encoding:
                    value = TextIOWrapper(value, encoding=encoding, errors=errors)
            setattr(self, name, value)

        if stdin == PIPE:
            self.stdin = Mock()
            for method in 'write', 'close':
                record_writes = partial(self._record, ('stdin', method))
                getattr(self.stdin, method).side_effect = record_writes

        self.pid: int = behaviour.pid
        #: The return code of this mock process.
        self.returncode: Optional[int] = None
        self.args: Command = args

    def _record(self, names, *args, **kw):
        for mock in self.class_instance_mock, self.mock:
            reduce(getattr, names, mock)(*args, **kw)
        for base_call, store in (
            (call, self.calls),
            (self.root_call, self.all_calls)
        ):
            store.append(reduce(getattr, names, base_call)(*args, **kw))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.wait()
        for stream in self.stdout, self.stderr:
            if stream:
                stream.close()

    @record
    def wait(self, timeout: float = None) -> int:
        "Simulate calls to :meth:`subprocess.Popen.wait`"
        self.returncode = self.behaviour.returncode
        return self.returncode

    @record
    def communicate(self, input: AnyStr = None, timeout: float = None) -> Tuple[AnyStr, AnyStr]:
        "Simulate calls to :meth:`subprocess.Popen.communicate`"
        self.returncode = self.behaviour.returncode
        return (self.stdout and self.stdout.read(),
                self.stderr and self.stderr.read())

    @record
    def poll(self) -> Optional[int]:
        "Simulate calls to :meth:`subprocess.Popen.poll`"
        while self.poll_count and self.returncode is None:
            self.poll_count -= 1
            return None
        # This call to wait() is NOT how poll() behaves in reality.
        # poll() NEVER sets the returncode.
        # The returncode is *only* ever set by process completion.
        # The following is an artifact of the fixture's implementation.
        self.returncode = self.behaviour.returncode
        return self.returncode

    @record
    def send_signal(self, signal: int) -> None:
        "Simulate calls to :meth:`subprocess.Popen.send_signal`"
        pass

    @record
    def terminate(self) -> None:
        "Simulate calls to :meth:`subprocess.Popen.terminate`"
        pass

    @record
    def kill(self) -> None:
        "Simulate calls to :meth:`subprocess.Popen.kill`"
        pass


class MockPopen(object):
    """
    A specialised mock for testing use of :class:`subprocess.Popen`.
    An instance of this class can be used in place of the
    :class:`subprocess.Popen` and is often inserted where it's needed using
    :func:`unittest.mock.patch` or a :class:`~testfixtures.Replacer`.
    """

    default_behaviour: PopenBehaviour = None

    def __init__(self):
        self.commands: Dict[str, PopenBehaviour] = {}
        self.mock: Mock = Mock()
        #: All calls made using this mock and the objects it returns, represented using
        #: :func:`~unittest.mock.call` instances.
        self.all_calls: List[Call] = []

    def _resolve_behaviour(self, stdout, stderr, returncode,
                           pid, poll_count, behaviour):
        if behaviour is None:
            return PopenBehaviour(
                stdout, stderr, returncode, pid, poll_count
            )
        else:
            return behaviour

    def set_command(
            self,
            command: str,
            stdout: bytes = b'',
            stderr: bytes = b'',
            returncode: int = 0,
            pid: int = 1234,
            poll_count: int = 3,
            behaviour: Union[PopenBehaviour, Callable] = None
    ):
        """
        Set the behaviour of this mock when it is used to simulate the
        specified command.

        :param command: A :class:`str` representing the command to be simulated.
        """
        self.commands[shell_join(command)] = self._resolve_behaviour(
            stdout, stderr, returncode, pid, poll_count, behaviour
        )

    def set_default(self, stdout=b'', stderr=b'', returncode=0,
                    pid=1234, poll_count=3, behaviour=None):
        """
        Set the behaviour of this mock when it is used to simulate commands
        that have no explicit behavior specified using
        :meth:`~MockPopen.set_command`.
        """
        self.default_behaviour = self._resolve_behaviour(
            stdout, stderr, returncode, pid, poll_count, behaviour
        )

    def __call__(self, *args, **kw):
        self.mock.Popen(*args, **kw)
        root_call = call.Popen(*args, **kw)
        self.all_calls.append(root_call)
        return MockPopenInstance(self, root_call, *args, **kw)


set_command_params = """
:param stdout:
    :class:`bytes` representing the simulated content written by the process
    to the stdout pipe.
:param stderr:
    :class:`bytes` representing the simulated content written by the process
    to the stderr pipe.
:param returncode:
    An integer representing the return code of the simulated process.
:param pid:
    An integer representing the process identifier of the simulated
    process. This is useful if you have code the prints out the pids
    of running processes.
:param poll_count:
    Specifies the number of times :meth:`~MockPopenInstance.poll` can be
    called before :attr:`~MockPopenInstance.returncode` is set and returned
    by :meth:`~MockPopenInstance.poll`.

If supplied, ``behaviour`` must be either a :class:`PopenBehaviour`
instance or a callable that takes the ``command`` string representing
the command to be simulated and the ``stdin`` supplied when instantiating
the :class:`subprocess.Popen` with that command and should
return a :class:`PopenBehaviour` instance.
"""


# add the param docs, so we only have one copy of them!
extend_docstring(set_command_params,
                 [MockPopen.set_command, MockPopen.set_default])

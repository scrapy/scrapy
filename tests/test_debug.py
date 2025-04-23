import signal
from unittest.mock import MagicMock, patch

from scrapy.extensions.debug import Debugger, StackTraceDump


def test_stack_trace_dump_initialization():
    crawler_mock = MagicMock()
    with patch("signal.signal") as mock_signal:
        stack_trace_dump = StackTraceDump(crawler_mock)
        assert stack_trace_dump.crawler == crawler_mock
        mock_signal.assert_any_call(signal.SIGUSR2, stack_trace_dump.dump_stacktrace)
        mock_signal.assert_any_call(signal.SIGQUIT, stack_trace_dump.dump_stacktrace)


def test_stack_trace_dump_initialization_with_attribute_error():
    crawler_mock = MagicMock()
    with patch("signal.signal", side_effect=AttributeError) as mock_signal:
        stack_trace_dump = StackTraceDump(crawler_mock)
        assert stack_trace_dump.crawler == crawler_mock
        mock_signal.assert_called_once_with(
            signal.SIGUSR2, stack_trace_dump.dump_stacktrace
        )


def test_stack_trace_dump_stacktrace_logging():
    crawler_mock = MagicMock()
    crawler_mock.engine = MagicMock()
    with (
        patch(
            "scrapy.extensions.debug.format_engine_status",
            return_value="engine_status_mock",
        ),
        patch(
            "scrapy.extensions.debug.format_live_refs", return_value="live_refs_mock"
        ),
        patch(
            "scrapy.extensions.debug.StackTraceDump._thread_stacks",
            return_value="thread_stacks_mock",
        ),
        patch("logging.Logger.info") as mock_logger_info,
    ):
        stack_trace_dump = StackTraceDump(crawler_mock)
        stack_trace_dump.dump_stacktrace(signal.SIGUSR2, None)

        mock_logger_info.assert_called_once_with(
            "Dumping stack trace and engine status\n"
            "%(enginestatus)s\n%(liverefs)s\n%(stackdumps)s",
            {
                "stackdumps": "thread_stacks_mock",
                "enginestatus": "engine_status_mock",
                "liverefs": "live_refs_mock",
            },
            extra={"crawler": crawler_mock},
        )


def test_stack_trace_dump_thread_stacks():
    with (
        patch("sys._current_frames", return_value={1: MagicMock(), 2: MagicMock()}),
        patch(
            "threading.enumerate",
            return_value=[
                MagicMock(ident=1, name="Thread-1"),
                MagicMock(ident=2, name="Thread-2"),
            ],
        ),
        patch("traceback.format_stack", side_effect=lambda frame: [f"frame-{frame}"]),
    ):
        stack_trace_dump = StackTraceDump(MagicMock())
        result = stack_trace_dump._thread_stacks()
        print(result)
        assert "Thread: <MagicMock name='Thread-1.name'" in result
        assert "Thread: <MagicMock name='Thread-2.name'" in result


def test_stack_trace_dump_from_crawler_instance_creation():
    crawler_mock = MagicMock()
    stack_trace_dump = StackTraceDump.from_crawler(crawler_mock)
    assert isinstance(stack_trace_dump, StackTraceDump)
    assert stack_trace_dump.crawler == crawler_mock


def test_debugger_initialization():
    with patch("signal.signal") as mock_signal:
        debugger = Debugger()
        mock_signal.assert_called_once_with(signal.SIGUSR2, debugger._enter_debugger)


def test_debugger_enter_debugger():
    with patch("pdb.Pdb.set_trace") as mock_set_trace:
        debugger = Debugger()
        frame_mock = MagicMock()
        debugger._enter_debugger(signal.SIGUSR2, frame_mock)
        mock_set_trace.assert_called_once_with(frame_mock.f_back)

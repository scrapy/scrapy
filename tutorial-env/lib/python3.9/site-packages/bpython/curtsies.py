# To gradually migrate to mypy we aren't setting these globally yet
# mypy: disallow_untyped_defs=True
# mypy: disallow_untyped_calls=True

import argparse
import collections
import logging
import sys

import curtsies
import curtsies.events
import curtsies.input
import curtsies.window

from . import args as bpargs, translations, inspection
from .config import Config
from .curtsiesfrontend import events
from .curtsiesfrontend.coderunner import SystemExitFromCodeRunner
from .curtsiesfrontend.interpreter import Interp
from .curtsiesfrontend.repl import BaseRepl
from .repl import extract_exit_value
from .translations import _

from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)
from ._typing_compat import Protocol

logger = logging.getLogger(__name__)


class SupportsEventGeneration(Protocol):
    def send(
        self, timeout: Optional[float]
    ) -> Union[str, curtsies.events.Event, None]:
        ...

    def __iter__(self) -> "SupportsEventGeneration":
        ...

    def __next__(self) -> Union[str, curtsies.events.Event, None]:
        ...


class FullCurtsiesRepl(BaseRepl):
    def __init__(
        self,
        config: Config,
        locals_: Optional[Dict[str, Any]] = None,
        banner: Optional[str] = None,
        interp: Optional[Interp] = None,
    ) -> None:
        self.input_generator = curtsies.input.Input(
            keynames="curtsies", sigint_event=True, paste_threshold=None
        )
        window = curtsies.window.CursorAwareWindow(
            sys.stdout,
            sys.stdin,
            keep_last_line=True,
            hide_cursor=False,
            extra_bytes_callback=self.input_generator.unget_bytes,
        )

        self._request_refresh_callback: Callable[
            [], None
        ] = self.input_generator.event_trigger(events.RefreshRequestEvent)
        self._schedule_refresh_callback = (
            self.input_generator.scheduled_event_trigger(
                events.ScheduledRefreshRequestEvent
            )
        )
        self._request_reload_callback = (
            self.input_generator.threadsafe_event_trigger(events.ReloadEvent)
        )
        self._interrupting_refresh_callback = (
            self.input_generator.threadsafe_event_trigger(lambda: None)
        )
        self._request_undo_callback = self.input_generator.event_trigger(
            events.UndoEvent
        )

        with self.input_generator:
            pass  # temp hack to get .original_stty

        super().__init__(
            config,
            window,
            locals_=locals_,
            banner=banner,
            interp=interp,
            orig_tcattrs=self.input_generator.original_stty,
        )

    def _request_refresh(self) -> None:
        return self._request_refresh_callback()

    def _schedule_refresh(self, when: float) -> None:
        return self._schedule_refresh_callback(when)

    def _request_reload(self, files_modified: Sequence[str]) -> None:
        return self._request_reload_callback(files_modified=files_modified)

    def interrupting_refresh(self) -> None:
        return self._interrupting_refresh_callback()

    def request_undo(self, n: int = 1) -> None:
        return self._request_undo_callback(n=n)

    def get_term_hw(self) -> Tuple[int, int]:
        return self.window.get_term_hw()

    def get_cursor_vertical_diff(self) -> int:
        return self.window.get_cursor_vertical_diff()

    def get_top_usable_line(self) -> int:
        return self.window.top_usable_row

    def on_suspend(self) -> None:
        self.window.__exit__(None, None, None)
        self.input_generator.__exit__(None, None, None)

    def after_suspend(self) -> None:
        self.input_generator.__enter__()
        self.window.__enter__()
        self.interrupting_refresh()

    def process_event_and_paint(
        self, e: Union[str, curtsies.events.Event, None]
    ) -> None:
        """If None is passed in, just paint the screen"""
        try:
            if e is not None:
                self.process_event(e)
        except (SystemExitFromCodeRunner, SystemExit) as err:
            array, cursor_pos = self.paint(
                about_to_exit=True,
                user_quit=isinstance(err, SystemExitFromCodeRunner),
            )
            scrolled = self.window.render_to_terminal(array, cursor_pos)
            self.scroll_offset += scrolled
            raise
        else:
            array, cursor_pos = self.paint()
            scrolled = self.window.render_to_terminal(array, cursor_pos)
            self.scroll_offset += scrolled

    def mainloop(
        self,
        interactive: bool = True,
        paste: Optional[curtsies.events.PasteEvent] = None,
    ) -> None:
        if interactive:
            # Add custom help command
            # TODO: add methods to run the code
            self.initialize_interp()

            # run startup file
            self.process_event(events.RunStartupFileEvent())

        # handle paste
        if paste:
            self.process_event(paste)

        # do a display before waiting for first event
        self.process_event_and_paint(None)
        inputs = combined_events(self.input_generator)
        while self.module_gatherer.find_coroutine():
            e = inputs.send(0)
            if e is not None:
                self.process_event_and_paint(e)

        for e in inputs:
            self.process_event_and_paint(e)


def main(
    args: Optional[List[str]] = None,
    locals_: Optional[Dict[str, Any]] = None,
    banner: Optional[str] = None,
    welcome_message: Optional[str] = None,
) -> Any:
    """
    banner is displayed directly after the version information.
    welcome_message is passed on to Repl and displayed in the statusbar.
    """
    translations.init()

    def curtsies_arguments(parser: argparse._ArgumentGroup) -> None:
        parser.add_argument(
            "--paste",
            "-p",
            action="store_true",
            help=_("start by pasting lines of a file into session"),
        )

    config, options, exec_args = bpargs.parse(
        args,
        (
            _("curtsies arguments"),
            _("Additional arguments specific to the curtsies-based REPL."),
            curtsies_arguments,
        ),
    )

    interp = None
    paste = None
    exit_value: Tuple[Any, ...] = ()
    if exec_args:
        if not options:
            raise ValueError("don't pass in exec_args without options")
        if options.paste:
            paste = curtsies.events.PasteEvent()
            encoding = inspection.get_encoding_file(exec_args[0])
            with open(exec_args[0], encoding=encoding) as f:
                sourcecode = f.read()
            paste.events.extend(sourcecode)
        else:
            try:
                interp = Interp(locals=locals_)
                bpargs.exec_code(interp, exec_args)
            except SystemExit as e:
                exit_value = e.args
            if not options.interactive:
                return extract_exit_value(exit_value)
    else:
        # expected for interactive sessions (vanilla python does it)
        sys.path.insert(0, "")

    if not options.quiet:
        print(bpargs.version_banner())
    if banner is not None:
        print(banner)

    repl = FullCurtsiesRepl(config, locals_, welcome_message, interp)
    try:
        with repl.input_generator:
            with repl.window as win:
                with repl:
                    repl.height, repl.width = win.t.height, win.t.width
                    repl.mainloop(True, paste)
    except (SystemExitFromCodeRunner, SystemExit) as e:
        exit_value = e.args
    return extract_exit_value(exit_value)


def _combined_events(
    event_provider: SupportsEventGeneration, paste_threshold: int
) -> Generator[Union[str, curtsies.events.Event, None], Optional[float], None]:
    """Combines consecutive keypress events into paste events."""
    timeout = yield "nonsense_event"  # so send can be used immediately
    queue: collections.deque = collections.deque()
    while True:
        e = event_provider.send(timeout)
        if isinstance(e, curtsies.events.Event):
            timeout = yield e
            continue
        elif e is None:
            timeout = yield None
            continue
        else:
            queue.append(e)
        e = event_provider.send(0)
        while not (e is None or isinstance(e, curtsies.events.Event)):
            queue.append(e)
            e = event_provider.send(0)
        if len(queue) >= paste_threshold:
            paste = curtsies.events.PasteEvent()
            paste.events.extend(queue)
            queue.clear()
            timeout = yield paste
        else:
            while len(queue):
                timeout = yield queue.popleft()


def combined_events(
    event_provider: SupportsEventGeneration, paste_threshold: int = 3
) -> SupportsEventGeneration:
    g = _combined_events(event_provider, paste_threshold)
    next(g)
    return g


if __name__ == "__main__":
    sys.exit(main())

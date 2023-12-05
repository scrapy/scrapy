import greenlet
import time
from curtsies import events

from ..translations import _
from ..repl import Interaction
from ..curtsiesfrontend.events import RefreshRequestEvent
from ..curtsiesfrontend.manual_readline import edit_keys


class StatusBar(Interaction):
    """StatusBar and Interaction for Repl

    Passing of control back and forth between calls that use interact api
    (notify, confirm, file_prompt) like bpython.Repl.write2file and events on
    the main thread happens via those calls and
    self.wait_for_request_or_notify.

    Calling one of these three is required for the main thread to regain
    control!

    This is probably a terrible idea, and better would be rewriting this
    functionality in a evented or callback style, but trying to integrate
    bpython.Repl code.
    """

    def __init__(
        self,
        config,
        permanent_text="",
        request_refresh=lambda: None,
        schedule_refresh=lambda when: None,
    ):
        self._current_line = ""
        self.cursor_offset_in_line = 0
        self.in_prompt = False
        self.in_confirm = False
        self.waiting_for_refresh = False
        self.prompt = ""
        self._message = ""
        self.message_start_time = time.time()
        self.message_time = 3.0
        self.permanent_stack = []
        if permanent_text:
            self.permanent_stack.append(permanent_text)
        self.main_context = greenlet.getcurrent()
        self.request_context = None
        self.request_refresh = request_refresh
        self.schedule_refresh = schedule_refresh

        super().__init__(config)

    def push_permanent_message(self, msg):
        self._message = ""
        self.permanent_stack.append(msg)

    def pop_permanent_message(self, msg):
        if msg in self.permanent_stack:
            self.permanent_stack.remove(msg)
        else:
            raise ValueError("Message %r was not in permanent_stack" % msg)

    @property
    def has_focus(self):
        return self.in_prompt or self.in_confirm or self.waiting_for_refresh

    def message(self, msg, schedule_refresh=True):
        """Sets a temporary message"""
        self.message_start_time = time.time()
        self._message = msg
        if schedule_refresh:
            self.schedule_refresh(time.time() + self.message_time)

    def _check_for_expired_message(self):
        if (
            self._message
            and time.time() > self.message_start_time + self.message_time
        ):
            self._message = ""

    def process_event(self, e) -> None:
        """Returns True if shutting down"""
        assert self.in_prompt or self.in_confirm or self.waiting_for_refresh
        if isinstance(e, RefreshRequestEvent):
            self.waiting_for_refresh = False
            self.request_context.switch()
        elif isinstance(e, events.PasteEvent):
            for ee in e.events:
                # strip control seq
                self.add_normal_character(ee if len(ee) == 1 else ee[-1])
        elif e == "<ESC>" or isinstance(e, events.SigIntEvent):
            self.request_context.switch(False)
            self.escape()
        elif e in edit_keys:
            self.cursor_offset_in_line, self._current_line = edit_keys[e](
                self.cursor_offset_in_line, self._current_line
            )
        elif e == "<Ctrl-c>":  # TODO can this be removed?
            raise KeyboardInterrupt()
        elif e == "<Ctrl-d>":  # TODO this isn't a very intuitive behavior
            raise SystemExit()
        elif self.in_prompt and e in ("\n", "\r", "<Ctrl-j>", "Ctrl-m>"):
            line = self._current_line
            self.escape()
            self.request_context.switch(line)
        elif self.in_confirm:
            if e.lower() == _("y"):
                self.request_context.switch(True)
            else:
                self.request_context.switch(False)
            self.escape()
        else:  # add normal character
            self.add_normal_character(e)

    def add_normal_character(self, e):
        if e == "<SPACE>":
            e = " "
        if len(e) > 1:
            return
        self._current_line = (
            self._current_line[: self.cursor_offset_in_line]
            + e
            + self._current_line[self.cursor_offset_in_line :]
        )
        self.cursor_offset_in_line += 1

    def escape(self):
        """unfocus from statusbar, clear prompt state, wait for notify call"""
        self.in_prompt = False
        self.in_confirm = False
        self.prompt = ""
        self._current_line = ""

    @property
    def current_line(self):
        self._check_for_expired_message()
        if self.in_prompt:
            return self.prompt + self._current_line
        if self.in_confirm:
            return self.prompt
        if self._message:
            return self._message
        if self.permanent_stack:
            return self.permanent_stack[-1]
        return ""

    @property
    def should_show_message(self):
        return bool(self.current_line)

    # interaction interface - should be called from other greenlets
    def notify(self, msg, n=3.0, wait_for_keypress=False):
        self.request_context = greenlet.getcurrent()
        self.message_time = n
        self.message(msg, schedule_refresh=wait_for_keypress)
        self.waiting_for_refresh = True
        self.request_refresh()
        self.main_context.switch(msg)

    # below really ought to be called from greenlets other than main because
    # they block
    def confirm(self, q):
        """Expected to return True or False, given question prompt q"""
        self.request_context = greenlet.getcurrent()
        self.prompt = q
        self.in_confirm = True
        return self.main_context.switch(q)

    def file_prompt(self, s):
        """Expected to return a file name, given"""
        self.request_context = greenlet.getcurrent()
        self.prompt = s
        self.in_prompt = True
        return self.main_context.switch(s)

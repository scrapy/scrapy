from __future__ import absolute_import
from __future__ import division

import itertools
import sys
from signal import signal, SIGINT, default_int_handler

from pip.compat import WINDOWS
from pip.utils import format_size
from pip.utils.logging import get_indentation
from pip._vendor import six
from pip._vendor.progress.bar import Bar, IncrementalBar
from pip._vendor.progress.helpers import WritelnMixin
from pip._vendor.progress.spinner import Spinner

try:
    from pip._vendor import colorama
# Lots of different errors can come from this, including SystemError and
# ImportError.
except Exception:
    colorama = None


def _select_progress_class(preferred, fallback):
    encoding = getattr(preferred.file, "encoding", None)

    # If we don't know what encoding this file is in, then we'll just assume
    # that it doesn't support unicode and use the ASCII bar.
    if not encoding:
        return fallback

    # Collect all of the possible characters we want to use with the preferred
    # bar.
    characters = [
        getattr(preferred, "empty_fill", six.text_type()),
        getattr(preferred, "fill", six.text_type()),
    ]
    characters += list(getattr(preferred, "phases", []))

    # Try to decode the characters we're using for the bar using the encoding
    # of the given file, if this works then we'll assume that we can use the
    # fancier bar and if not we'll fall back to the plaintext bar.
    try:
        six.text_type().join(characters).encode(encoding)
    except UnicodeEncodeError:
        return fallback
    else:
        return preferred


_BaseBar = _select_progress_class(IncrementalBar, Bar)


class InterruptibleMixin(object):
    """
    Helper to ensure that self.finish() gets called on keyboard interrupt.

    This allows downloads to be interrupted without leaving temporary state
    (like hidden cursors) behind.

    This class is similar to the progress library's existing SigIntMixin
    helper, but as of version 1.2, that helper has the following problems:

    1. It calls sys.exit().
    2. It discards the existing SIGINT handler completely.
    3. It leaves its own handler in place even after an uninterrupted finish,
       which will have unexpected delayed effects if the user triggers an
       unrelated keyboard interrupt some time after a progress-displaying
       download has already completed, for example.
    """

    def __init__(self, *args, **kwargs):
        """
        Save the original SIGINT handler for later.
        """
        super(InterruptibleMixin, self).__init__(*args, **kwargs)

        self.original_handler = signal(SIGINT, self.handle_sigint)

        # If signal() returns None, the previous handler was not installed from
        # Python, and we cannot restore it. This probably should not happen,
        # but if it does, we must restore something sensible instead, at least.
        # The least bad option should be Python's default SIGINT handler, which
        # just raises KeyboardInterrupt.
        if self.original_handler is None:
            self.original_handler = default_int_handler

    def finish(self):
        """
        Restore the original SIGINT handler after finishing.

        This should happen regardless of whether the progress display finishes
        normally, or gets interrupted.
        """
        super(InterruptibleMixin, self).finish()
        signal(SIGINT, self.original_handler)

    def handle_sigint(self, signum, frame):
        """
        Call self.finish() before delegating to the original SIGINT handler.

        This handler should only be in place while the progress display is
        active.
        """
        self.finish()
        self.original_handler(signum, frame)


class DownloadProgressMixin(object):

    def __init__(self, *args, **kwargs):
        super(DownloadProgressMixin, self).__init__(*args, **kwargs)
        self.message = (" " * (get_indentation() + 2)) + self.message

    @property
    def downloaded(self):
        return format_size(self.index)

    @property
    def download_speed(self):
        # Avoid zero division errors...
        if self.avg == 0.0:
            return "..."
        return format_size(1 / self.avg) + "/s"

    @property
    def pretty_eta(self):
        if self.eta:
            return "eta %s" % self.eta_td
        return ""

    def iter(self, it, n=1):
        for x in it:
            yield x
            self.next(n)
        self.finish()


class WindowsMixin(object):

    def __init__(self, *args, **kwargs):
        # The Windows terminal does not support the hide/show cursor ANSI codes
        # even with colorama. So we'll ensure that hide_cursor is False on
        # Windows.
        # This call neds to go before the super() call, so that hide_cursor
        # is set in time. The base progress bar class writes the "hide cursor"
        # code to the terminal in its init, so if we don't set this soon
        # enough, we get a "hide" with no corresponding "show"...
        if WINDOWS and self.hide_cursor:
            self.hide_cursor = False

        super(WindowsMixin, self).__init__(*args, **kwargs)

        # Check if we are running on Windows and we have the colorama module,
        # if we do then wrap our file with it.
        if WINDOWS and colorama:
            self.file = colorama.AnsiToWin32(self.file)
            # The progress code expects to be able to call self.file.isatty()
            # but the colorama.AnsiToWin32() object doesn't have that, so we'll
            # add it.
            self.file.isatty = lambda: self.file.wrapped.isatty()
            # The progress code expects to be able to call self.file.flush()
            # but the colorama.AnsiToWin32() object doesn't have that, so we'll
            # add it.
            self.file.flush = lambda: self.file.wrapped.flush()


class DownloadProgressBar(WindowsMixin, InterruptibleMixin,
                          DownloadProgressMixin, _BaseBar):

    file = sys.stdout
    message = "%(percent)d%%"
    suffix = "%(downloaded)s %(download_speed)s %(pretty_eta)s"


class DownloadProgressSpinner(WindowsMixin, InterruptibleMixin,
                              DownloadProgressMixin, WritelnMixin, Spinner):

    file = sys.stdout
    suffix = "%(downloaded)s %(download_speed)s"

    def next_phase(self):
        if not hasattr(self, "_phaser"):
            self._phaser = itertools.cycle(self.phases)
        return next(self._phaser)

    def update(self):
        message = self.message % self
        phase = self.next_phase()
        suffix = self.suffix % self
        line = ''.join([
            message,
            " " if message else "",
            phase,
            " " if suffix else "",
            suffix,
        ])

        self.writeln(line)

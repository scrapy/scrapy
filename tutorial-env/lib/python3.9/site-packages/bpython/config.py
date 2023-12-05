# The MIT License
#
# Copyright (c) 2009-2015 the bpython authors.
# Copyright (c) 2015-2022 Sebastian Ramacher
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

# To gradually migrate to mypy we aren't setting these globally yet
# mypy: disallow_untyped_defs=True
# mypy: disallow_untyped_calls=True

import os
import sys
import locale
from configparser import ConfigParser
from itertools import chain
from pathlib import Path
from typing import MutableMapping, Mapping, Any, Dict
from xdg import BaseDirectory

from .autocomplete import AutocompleteModes

default_completion = AutocompleteModes.SIMPLE
# All supported letters for colors for themes
#
# Instead of importing it from .curtsiesfrontend.parse, we define them here to
# avoid a potential import of fcntl on Windows.
COLOR_LETTERS = tuple("krgybmcwd")


class UnknownColorCode(Exception):
    def __init__(self, key: str, color: str) -> None:
        self.key = key
        self.color = color


def getpreferredencoding() -> str:
    """Get the user's preferred encoding."""
    return locale.getpreferredencoding() or sys.getdefaultencoding()


def can_encode(c: str) -> bool:
    try:
        c.encode(getpreferredencoding())
        return True
    except UnicodeEncodeError:
        return False


def supports_box_chars() -> bool:
    """Check if the encoding supports Unicode box characters."""
    return all(map(can_encode, "│─└┘┌┐"))


def get_config_home() -> Path:
    """Returns the base directory for bpython's configuration files."""
    return Path(BaseDirectory.xdg_config_home) / "bpython"


def default_config_path() -> Path:
    """Returns bpython's default configuration file path."""
    return get_config_home() / "config"


def default_editor() -> str:
    """Returns the default editor."""
    return os.environ.get("VISUAL", os.environ.get("EDITOR", "vi"))


def fill_config_with_default_values(
    config: ConfigParser, default_values: Mapping[str, Mapping[str, Any]]
) -> None:
    for section in default_values.keys():
        if not config.has_section(section):
            config.add_section(section)

        for (opt, val) in default_values[section].items():
            if not config.has_option(section, opt):
                config.set(section, opt, str(val))


class Config:
    default_colors = {
        "keyword": "y",
        "name": "c",
        "comment": "b",
        "string": "m",
        "error": "r",
        "number": "G",
        "operator": "Y",
        "punctuation": "y",
        "token": "C",
        "background": "d",
        "output": "w",
        "main": "c",
        "paren": "R",
        "prompt": "c",
        "prompt_more": "g",
        "right_arrow_suggestion": "K",
    }

    defaults: Dict[str, Dict[str, Any]] = {
        "general": {
            "arg_spec": True,
            "auto_display_list": True,
            "autocomplete_mode": default_completion,
            "color_scheme": "default",
            "complete_magic_methods": True,
            "dedent_after": 1,
            "default_autoreload": False,
            "editor": default_editor(),
            "flush_output": True,
            "import_completion_skiplist": ":".join(
                (
                    # version tracking
                    ".git",
                    ".svn",
                    ".hg"
                    # XDG
                    ".config",
                    ".local",
                    ".share",
                    # nodejs
                    "node_modules",
                    # PlayOnLinux
                    "PlayOnLinux's virtual drives",
                    # wine
                    "dosdevices",
                    # Python byte code cache
                    "__pycache__",
                )
            ),
            "highlight_show_source": True,
            "hist_duplicates": True,
            "hist_file": "~/.pythonhist",
            "hist_length": 1000,
            "paste_time": 0.02,
            "pastebin_confirm": True,
            "pastebin_expiry": "1week",
            "pastebin_helper": "",
            "pastebin_url": "https://bpaste.net",
            "save_append_py": False,
            "single_undo_time": 1.0,
            "syntax": True,
            "tab_length": 4,
            "unicode_box": True,
            "brackets_completion": False,
        },
        "keyboard": {
            "backspace": "C-h",
            "beginning_of_line": "C-a",
            "clear_line": "C-u",
            "clear_screen": "C-l",
            "clear_word": "C-w",
            "copy_clipboard": "F10",
            "cut_to_buffer": "C-k",
            "delete": "C-d",
            "down_one_line": "C-n",
            "edit_config": "F3",
            "edit_current_block": "C-x",
            "end_of_line": "C-e",
            "exit": "",
            "external_editor": "F7",
            "help": "F1",
            "incremental_search": "M-s",
            "last_output": "F9",
            "left": "C-b",
            "pastebin": "F8",
            "redo": "C-g",
            "reimport": "F6",
            "reverse_incremental_search": "M-r",
            "right": "C-f",
            "save": "C-s",
            "search": "C-o",
            "show_source": "F2",
            "suspend": "C-z",
            "toggle_file_watch": "F5",
            "transpose_chars": "C-t",
            "undo": "C-r",
            "up_one_line": "C-p",
            "yank_from_buffer": "C-y",
        },
        "cli": {
            "suggestion_width": 0.8,
            "trim_prompts": False,
        },
        "curtsies": {
            "list_above": False,
            "right_arrow_completion": True,
        },
    }

    def __init__(self, config_path: Path) -> None:
        """Loads .ini configuration file and stores its values."""

        config = ConfigParser()
        fill_config_with_default_values(config, self.defaults)
        try:
            config.read(config_path)
        except UnicodeDecodeError as e:
            sys.stderr.write(
                "Error: Unable to parse config file at '{}' due to an "
                "encoding issue ({}). Please make sure to fix the encoding "
                "of the file or remove it and then try again.\n".format(
                    config_path, e
                )
            )
            sys.exit(1)

        default_keys_to_commands = {
            value: key for (key, value) in self.defaults["keyboard"].items()
        }

        def get_key_no_doublebind(command: str) -> str:
            default_commands_to_keys = self.defaults["keyboard"]
            requested_key = config.get("keyboard", command)

            try:
                default_command = default_keys_to_commands[requested_key]
                if default_commands_to_keys[default_command] == config.get(
                    "keyboard", default_command
                ):
                    setattr(self, f"{default_command}_key", "")
            except KeyError:
                pass

            return requested_key

        self.config_path = Path(config_path).absolute()
        self.hist_file = Path(config.get("general", "hist_file")).expanduser()

        self.dedent_after = config.getint("general", "dedent_after")
        self.tab_length = config.getint("general", "tab_length")
        self.auto_display_list = config.getboolean(
            "general", "auto_display_list"
        )
        self.syntax = config.getboolean("general", "syntax")
        self.arg_spec = config.getboolean("general", "arg_spec")
        self.paste_time = config.getfloat("general", "paste_time")
        self.single_undo_time = config.getfloat("general", "single_undo_time")
        self.highlight_show_source = config.getboolean(
            "general", "highlight_show_source"
        )
        self.editor = config.get("general", "editor")
        self.hist_length = config.getint("general", "hist_length")
        self.hist_duplicates = config.getboolean("general", "hist_duplicates")
        self.flush_output = config.getboolean("general", "flush_output")
        self.default_autoreload = config.getboolean(
            "general", "default_autoreload"
        )
        self.import_completion_skiplist = config.get(
            "general", "import_completion_skiplist"
        ).split(":")

        self.pastebin_key = get_key_no_doublebind("pastebin")
        self.copy_clipboard_key = get_key_no_doublebind("copy_clipboard")
        self.save_key = get_key_no_doublebind("save")
        self.search_key = get_key_no_doublebind("search")
        self.show_source_key = get_key_no_doublebind("show_source")
        self.suspend_key = get_key_no_doublebind("suspend")
        self.toggle_file_watch_key = get_key_no_doublebind("toggle_file_watch")
        self.undo_key = get_key_no_doublebind("undo")
        self.redo_key = get_key_no_doublebind("redo")
        self.reimport_key = get_key_no_doublebind("reimport")
        self.reverse_incremental_search_key = get_key_no_doublebind(
            "reverse_incremental_search"
        )
        self.incremental_search_key = get_key_no_doublebind(
            "incremental_search"
        )
        self.up_one_line_key = get_key_no_doublebind("up_one_line")
        self.down_one_line_key = get_key_no_doublebind("down_one_line")
        self.cut_to_buffer_key = get_key_no_doublebind("cut_to_buffer")
        self.yank_from_buffer_key = get_key_no_doublebind("yank_from_buffer")
        self.clear_word_key = get_key_no_doublebind("clear_word")
        self.backspace_key = get_key_no_doublebind("backspace")
        self.clear_line_key = get_key_no_doublebind("clear_line")
        self.clear_screen_key = get_key_no_doublebind("clear_screen")
        self.delete_key = get_key_no_doublebind("delete")

        self.left_key = get_key_no_doublebind("left")
        self.right_key = get_key_no_doublebind("right")
        self.end_of_line_key = get_key_no_doublebind("end_of_line")
        self.beginning_of_line_key = get_key_no_doublebind("beginning_of_line")
        self.transpose_chars_key = get_key_no_doublebind("transpose_chars")
        self.exit_key = get_key_no_doublebind("exit")
        self.last_output_key = get_key_no_doublebind("last_output")
        self.edit_config_key = get_key_no_doublebind("edit_config")
        self.edit_current_block_key = get_key_no_doublebind(
            "edit_current_block"
        )
        self.external_editor_key = get_key_no_doublebind("external_editor")
        self.help_key = get_key_no_doublebind("help")

        self.pastebin_confirm = config.getboolean("general", "pastebin_confirm")
        self.pastebin_url = config.get("general", "pastebin_url")
        self.pastebin_expiry = config.get("general", "pastebin_expiry")
        self.pastebin_helper = config.get("general", "pastebin_helper")

        self.cli_suggestion_width = config.getfloat("cli", "suggestion_width")
        self.cli_trim_prompts = config.getboolean("cli", "trim_prompts")

        self.complete_magic_methods = config.getboolean(
            "general", "complete_magic_methods"
        )
        self.autocomplete_mode = (
            AutocompleteModes.from_string(
                config.get("general", "autocomplete_mode")
            )
            or default_completion
        )
        self.save_append_py = config.getboolean("general", "save_append_py")

        self.curtsies_list_above = config.getboolean("curtsies", "list_above")
        self.curtsies_right_arrow_completion = config.getboolean(
            "curtsies", "right_arrow_completion"
        )
        self.unicode_box = config.getboolean("general", "unicode_box")

        self.color_scheme = dict()
        color_scheme_name = config.get("general", "color_scheme")
        if color_scheme_name == "default":
            self.color_scheme.update(self.default_colors)
        else:
            path = get_config_home() / f"{color_scheme_name}.theme"
            try:
                load_theme(path, self.color_scheme, self.default_colors)
            except OSError:
                sys.stderr.write(
                    f"Could not load theme '{color_scheme_name}' from {path}.\n"
                )
                sys.exit(1)
            except UnknownColorCode as ucc:
                sys.stderr.write(
                    f"Theme '{color_scheme_name}' contains invalid color: {ucc.key} = {ucc.color}.\n"
                )
                sys.exit(1)

        # set box drawing characters
        (
            self.left_border,
            self.right_border,
            self.top_border,
            self.bottom_border,
            self.left_bottom_corner,
            self.right_bottom_corner,
            self.left_top_corner,
            self.right_top_corner,
        ) = (
            ("│", "│", "─", "─", "└", "┘", "┌", "┐")
            if self.unicode_box and supports_box_chars()
            else ("|", "|", "-", "-", "+", "+", "+", "+")
        )
        self.brackets_completion = config.getboolean(
            "general", "brackets_completion"
        )


def load_theme(
    path: Path,
    colors: MutableMapping[str, str],
    default_colors: Mapping[str, str],
) -> None:
    theme = ConfigParser()
    with open(path) as f:
        theme.read_file(f)
    for k, v in chain(theme.items("syntax"), theme.items("interface")):
        if theme.has_option("syntax", k):
            colors[k] = theme.get("syntax", k)
        else:
            colors[k] = theme.get("interface", k)
        if colors[k].lower() not in COLOR_LETTERS:
            raise UnknownColorCode(k, colors[k])

    # Check against default theme to see if all values are defined
    for k, v in default_colors.items():
        if k not in colors:
            colors[k] = v

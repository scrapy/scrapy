# The MIT License
#
# Copyright (c) 2008 Simon de Vlieger
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

import string
from typing import TypeVar, Generic, Tuple, Dict

T = TypeVar("T")


class KeyMap(Generic[T]):
    def __init__(self, default: T) -> None:
        self.map: Dict[str, T] = {}
        self.default = default

    def __getitem__(self, key: str) -> T:
        if not key:
            # Unbound key
            return self.default
        elif key in self.map:
            return self.map[key]
        else:
            raise KeyError(
                f"Configured keymap ({key}) does not exist in bpython.keys"
            )

    def __delitem__(self, key: str):
        del self.map[key]

    def __setitem__(self, key: str, value: T):
        self.map[key] = value


cli_key_dispatch: KeyMap[Tuple[str, ...]] = KeyMap(tuple())
urwid_key_dispatch = KeyMap("")

# fill dispatch with letters
for c in string.ascii_lowercase:
    cli_key_dispatch[f"C-{c}"] = (
        chr(string.ascii_lowercase.index(c) + 1),
        f"^{c.upper()}",
    )

for c in string.ascii_lowercase:
    urwid_key_dispatch[f"C-{c}"] = f"ctrl {c}"
    urwid_key_dispatch[f"M-{c}"] = f"meta {c}"

# fill dispatch with cool characters
cli_key_dispatch["C-["] = (chr(27), "^[")
cli_key_dispatch["C-\\"] = (chr(28), "^\\")
cli_key_dispatch["C-]"] = (chr(29), "^]")
cli_key_dispatch["C-^"] = (chr(30), "^^")
cli_key_dispatch["C-_"] = (chr(31), "^_")

# fill dispatch with function keys
for x in range(1, 13):
    cli_key_dispatch[f"F{x}"] = (f"KEY_F({x})",)

for x in range(1, 13):
    urwid_key_dispatch[f"F{x}"] = f"f{x}"

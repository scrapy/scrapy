"""Mapping of config file names of keys to curtsies names

In the style of bpython config files and keymap"""

from typing import Tuple

SPECIALS = {
    "C-[": "<ESC>",
    "C-^": "<Ctrl-6>",
    "C-_": "<Ctrl-/>",
}


# TODO make a precalculated version of this
class KeyMap:
    """Maps config file key syntax to Curtsies names"""

    def __getitem__(self, key: str) -> Tuple[str, ...]:
        if not key:  # Unbound key
            return ()
        elif key in SPECIALS:
            return (SPECIALS[key],)
        elif key[1:] and key[:2] == "C-":
            return ("<Ctrl-%s>" % key[2:],)
        elif key[1:] and key[:2] == "M-":
            return (
                "<Esc+%s>" % key[2:],
                "<Meta-%s>" % key[2:],
            )
        elif key[0] == "F" and key[1:].isdigit():
            return ("<F%d>" % int(key[1:]),)
        else:
            raise KeyError(
                "Configured keymap (%s)" % key + " does not exist in bpython.keys"
            )


keymap = KeyMap()

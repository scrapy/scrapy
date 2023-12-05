import unittest

from bpython import keys


class TestCLIKeys(unittest.TestCase):
    def test_keymap_map(self):
        """Verify KeyMap.map being a dictionary with the correct
        length."""
        self.assertEqual(len(keys.cli_key_dispatch.map), 43)

    def test_keymap_setitem(self):
        """Verify keys.KeyMap correctly setting items."""
        keys.cli_key_dispatch["simon"] = "awesome"
        self.assertEqual(keys.cli_key_dispatch["simon"], "awesome")

    def test_keymap_delitem(self):
        """Verify keys.KeyMap correctly removing items."""
        keys.cli_key_dispatch["simon"] = "awesome"
        del keys.cli_key_dispatch["simon"]
        if "simon" in keys.cli_key_dispatch.map:
            raise Exception("Key still exists in dictionary")

    def test_keymap_getitem(self):
        """Verify keys.KeyMap correctly looking up items."""
        self.assertEqual(keys.cli_key_dispatch["C-["], (chr(27), "^["))
        self.assertEqual(keys.cli_key_dispatch["F11"], ("KEY_F(11)",))
        self.assertEqual(keys.cli_key_dispatch["C-a"], ("\x01", "^A"))

    def test_keymap_keyerror(self):
        """Verify keys.KeyMap raising KeyError when getting undefined key"""
        with self.assertRaises(KeyError):
            keys.cli_key_dispatch["C-asdf"]
            keys.cli_key_dispatch["C-qwerty"]


class TestUrwidKeys(unittest.TestCase):
    def test_keymap_map(self):
        """Verify KeyMap.map being a dictionary with the correct
        length."""
        self.assertEqual(len(keys.urwid_key_dispatch.map), 64)

    def test_keymap_setitem(self):
        """Verify keys.KeyMap correctly setting items."""
        keys.urwid_key_dispatch["simon"] = "awesome"
        self.assertEqual(keys.urwid_key_dispatch["simon"], "awesome")

    def test_keymap_delitem(self):
        """Verify keys.KeyMap correctly removing items."""
        keys.urwid_key_dispatch["simon"] = "awesome"
        del keys.urwid_key_dispatch["simon"]
        if "simon" in keys.urwid_key_dispatch.map:
            raise Exception("Key still exists in dictionary")

    def test_keymap_getitem(self):
        """Verify keys.KeyMap correctly looking up items."""
        self.assertEqual(keys.urwid_key_dispatch["F11"], "f11")
        self.assertEqual(keys.urwid_key_dispatch["C-a"], "ctrl a")
        self.assertEqual(keys.urwid_key_dispatch["M-a"], "meta a")

    def test_keymap_keyerror(self):
        """Verify keys.KeyMap raising KeyError when getting undefined key"""
        with self.assertRaises(KeyError):
            keys.urwid_key_dispatch["C-asdf"]
            keys.urwid_key_dispatch["C-qwerty"]


if __name__ == "__main__":
    unittest.main()

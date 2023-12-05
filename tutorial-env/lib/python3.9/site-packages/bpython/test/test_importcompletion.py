import os
import tempfile
import unittest

from pathlib import Path
from bpython.importcompletion import ModuleGatherer


class TestSimpleComplete(unittest.TestCase):
    def setUp(self):
        self.module_gatherer = ModuleGatherer()
        self.module_gatherer.modules = [
            "zzabc",
            "zzabd",
            "zzefg",
            "zzabc.e",
            "zzabc.f",
            "zzefg.a1",
            "zzefg.a2",
        ]

    def test_simple_completion(self):
        self.assertSetEqual(
            self.module_gatherer.complete(10, "import zza"), {"zzabc", "zzabd"}
        )
        self.assertSetEqual(
            self.module_gatherer.complete(11, "import  zza"), {"zzabc", "zzabd"}
        )

    def test_import_empty(self):
        self.assertSetEqual(
            self.module_gatherer.complete(13, "import zzabc."),
            {"zzabc.e", "zzabc.f"},
        )
        self.assertSetEqual(
            self.module_gatherer.complete(14, "import  zzabc."),
            {"zzabc.e", "zzabc.f"},
        )

    def test_import(self):
        self.assertSetEqual(
            self.module_gatherer.complete(14, "import zzefg.a"),
            {"zzefg.a1", "zzefg.a2"},
        )
        self.assertSetEqual(
            self.module_gatherer.complete(15, "import  zzefg.a"),
            {"zzefg.a1", "zzefg.a2"},
        )

    @unittest.expectedFailure
    def test_import_blank(self):
        self.assertSetEqual(
            self.module_gatherer.complete(7, "import "),
            {"zzabc", "zzabd", "zzefg"},
        )
        self.assertSetEqual(
            self.module_gatherer.complete(8, "import  "),
            {"zzabc", "zzabd", "zzefg"},
        )

    @unittest.expectedFailure
    def test_from_import_empty(self):
        self.assertSetEqual(
            self.module_gatherer.complete(5, "from "),
            {"zzabc", "zzabd", "zzefg"},
        )
        self.assertSetEqual(
            self.module_gatherer.complete(6, "from  "),
            {"zzabc", "zzabd", "zzefg"},
        )

    @unittest.expectedFailure
    def test_from_module_import_empty(self):
        self.assertSetEqual(
            self.module_gatherer.complete(18, "from zzabc import "), {"e", "f"}
        )
        self.assertSetEqual(
            self.module_gatherer.complete(19, "from  zzabc import "), {"e", "f"}
        )
        self.assertSetEqual(
            self.module_gatherer.complete(19, "from zzabc  import "), {"e", "f"}
        )
        self.assertSetEqual(
            self.module_gatherer.complete(19, "from zzabc import  "), {"e", "f"}
        )

    def test_from_module_import(self):
        self.assertSetEqual(
            self.module_gatherer.complete(19, "from zzefg import a"),
            {"a1", "a2"},
        )
        self.assertSetEqual(
            self.module_gatherer.complete(20, "from  zzefg import a"),
            {"a1", "a2"},
        )
        self.assertSetEqual(
            self.module_gatherer.complete(20, "from zzefg  import a"),
            {"a1", "a2"},
        )
        self.assertSetEqual(
            self.module_gatherer.complete(20, "from zzefg import  a"),
            {"a1", "a2"},
        )


class TestRealComplete(unittest.TestCase):
    def setUp(self):
        self.module_gatherer = ModuleGatherer()
        while self.module_gatherer.find_coroutine():
            pass
        __import__("sys")
        __import__("os")

    def test_from_attribute(self):
        self.assertSetEqual(
            self.module_gatherer.complete(19, "from sys import arg"), {"argv"}
        )

    def test_from_attr_module(self):
        self.assertSetEqual(
            self.module_gatherer.complete(9, "from os.p"), {"os.path"}
        )

    def test_from_package(self):
        self.assertSetEqual(
            self.module_gatherer.complete(17, "from xml import d"), {"dom"}
        )


class TestAvoidSymbolicLinks(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as import_test_folder:
            base_path = Path(import_test_folder)
            (base_path / "Level0" / "Level1" / "Level2").mkdir(parents=True)
            (base_path / "Left").mkdir(parents=True)
            (base_path / "Right").mkdir(parents=True)

            current_path = base_path / "Level0"
            (current_path / "__init__.py").touch()

            current_path = current_path / "Level1"
            (current_path / "__init__.py").touch()

            current_path = current_path / "Level2"
            (current_path / "__init__.py").touch()
            # Level0/Level1/Level2/Level3 -> Level0/Level1
            (current_path / "Level3").symlink_to(
                base_path / "Level0" / "Level1", target_is_directory=True
            )

            current_path = base_path / "Right"
            (current_path / "__init__.py").touch()
            # Right/toLeft -> Left
            (current_path / "toLeft").symlink_to(
                base_path / "Left", target_is_directory=True
            )

            current_path = base_path / "Left"
            (current_path / "__init__.py").touch()
            # Left/toRight -> Right
            (current_path / "toRight").symlink_to(
                base_path / "Right", target_is_directory=True
            )

            self.module_gatherer = ModuleGatherer((base_path.absolute(),))
            while self.module_gatherer.find_coroutine():
                pass

    def test_simple_symbolic_link_loop(self):
        filepaths = [
            "Left.toRight.toLeft",
            "Left.toRight",
            "Left",
            "Level0.Level1.Level2.Level3",
            "Level0.Level1.Level2",
            "Level0.Level1",
            "Level0",
            "Right",
            "Right.toLeft",
            "Right.toLeft.toRight",
        ]

        for thing in self.module_gatherer.modules:
            self.assertIn(thing, filepaths)
            if thing == "Left.toRight.toLeft":
                filepaths.remove("Right.toLeft")
                filepaths.remove("Right.toLeft.toRight")
            if thing == "Right.toLeft.toRight":
                filepaths.remove("Left.toRight.toLeft")
                filepaths.remove("Left.toRight")
            filepaths.remove(thing)
        self.assertFalse(filepaths)


class TestBugReports(unittest.TestCase):
    def test_issue_847(self):
        with tempfile.TemporaryDirectory() as import_test_folder:
            #   ./xyzzy
            #   ./xyzzy/__init__.py
            #   ./xyzzy/plugh
            #   ./xyzzy/plugh/__init__.py
            #   ./xyzzy/plugh/bar.py
            #   ./xyzzy/plugh/foo.py

            base_path = Path(import_test_folder)
            (base_path / "xyzzy" / "plugh").mkdir(parents=True)
            (base_path / "xyzzy" / "__init__.py").touch()
            (base_path / "xyzzy" / "plugh" / "__init__.py").touch()
            (base_path / "xyzzy" / "plugh" / "bar.py").touch()
            (base_path / "xyzzy" / "plugh" / "foo.py").touch()

            module_gatherer = ModuleGatherer((base_path.absolute(),))
            while module_gatherer.find_coroutine():
                pass

            self.assertSetEqual(
                module_gatherer.complete(17, "from xyzzy.plugh."),
                {"xyzzy.plugh.bar", "xyzzy.plugh.foo"},
            )


if __name__ == "__main__":
    unittest.main()

import contextlib
import os
import shutil
import tempfile
import unittest
import warnings
from pathlib import Path

from scrapy.utils.misc import set_environ
from scrapy.utils.project import data_path, get_project_settings


@contextlib.contextmanager
def inside_a_project():
    prev_dir = os.getcwd()
    project_dir = tempfile.mkdtemp()

    try:
        os.chdir(project_dir)
        Path("scrapy.cfg").touch()

        yield project_dir
    finally:
        os.chdir(prev_dir)
        shutil.rmtree(project_dir)


class ProjectUtilsTest(unittest.TestCase):
    def test_data_path_outside_project(self):
        self.assertEqual(str(Path(".scrapy", "somepath")), data_path("somepath"))
        abspath = str(Path(os.path.sep, "absolute", "path"))
        self.assertEqual(abspath, data_path(abspath))

    def test_data_path_inside_project(self):
        with inside_a_project() as proj_path:
            expected = Path(proj_path, ".scrapy", "somepath")
            self.assertEqual(expected.resolve(), Path(data_path("somepath")).resolve())
            abspath = str(Path(os.path.sep, "absolute", "path").resolve())
            self.assertEqual(abspath, data_path(abspath))


class GetProjectSettingsTestCase(unittest.TestCase):
    def test_valid_envvar(self):
        value = "tests.test_cmdline.settings"
        envvars = {
            "SCRAPY_SETTINGS_MODULE": value,
        }
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with set_environ(**envvars):
                settings = get_project_settings()

        assert settings.get("SETTINGS_MODULE") == value

    def test_invalid_envvar(self):
        envvars = {
            "SCRAPY_FOO": "bar",
        }
        with set_environ(**envvars):
            settings = get_project_settings()

        assert settings.get("SCRAPY_FOO") is None

    def test_valid_and_invalid_envvars(self):
        value = "tests.test_cmdline.settings"
        envvars = {
            "SCRAPY_FOO": "bar",
            "SCRAPY_SETTINGS_MODULE": value,
        }
        with set_environ(**envvars):
            settings = get_project_settings()
        assert settings.get("SETTINGS_MODULE") == value
        assert settings.get("SCRAPY_FOO") is None

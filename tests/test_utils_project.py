import os
import warnings
from pathlib import Path

import pytest

from scrapy.utils.misc import set_environ
from scrapy.utils.project import data_path, get_project_settings


@pytest.fixture
def proj_path(tmp_path):
    prev_dir = Path.cwd()
    project_dir = tmp_path

    try:
        os.chdir(project_dir)
        Path("scrapy.cfg").touch()

        yield project_dir
    finally:
        os.chdir(prev_dir)


def test_data_path_outside_project():
    assert str(Path(".scrapy", "somepath")) == data_path("somepath")
    abspath = str(Path(os.path.sep, "absolute", "path"))
    assert abspath == data_path(abspath)


def test_data_path_inside_project(proj_path: Path) -> None:
    expected = proj_path / ".scrapy" / "somepath"
    assert expected.resolve() == Path(data_path("somepath")).resolve()
    abspath = str(Path(os.path.sep, "absolute", "path").resolve())
    assert abspath == data_path(abspath)


class TestGetProjectSettings:
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

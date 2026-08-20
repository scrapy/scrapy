from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import set_environ
from scrapy.utils.project import (
    data_path,
    get_project_settings,
    inside_project,
    project_data_dir,
)

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def proj_path(tmp_path: Path) -> Generator[Path]:
    prev_dir = Path.cwd()
    project_dir = tmp_path

    try:
        os.chdir(project_dir)
        Path("scrapy.cfg").touch()

        yield project_dir
    finally:
        os.chdir(prev_dir)


@pytest.fixture
def no_proj_path(tmp_path: Path) -> Generator[Path]:
    """A working directory without a scrapy.cfg file, also isolated from the
    user-wide and system-wide Scrapy configuration files."""
    prev_dir = Path.cwd()
    try:
        os.chdir(tmp_path)
        with set_environ(HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path)):
            yield tmp_path
    finally:
        os.chdir(prev_dir)


def test_data_path_outside_project() -> None:
    assert str(Path(".scrapy", "somepath")) == data_path("somepath")
    abspath = str(Path(os.path.sep, "absolute", "path"))
    assert abspath == data_path(abspath)


def test_data_path_inside_project(proj_path: Path) -> None:
    expected = proj_path / ".scrapy" / "somepath"
    assert expected.resolve() == Path(data_path("somepath")).resolve()
    abspath = str(Path(os.path.sep, "absolute", "path").resolve())
    assert abspath == data_path(abspath)


def test_data_path_createdir(no_proj_path: Path) -> None:
    path = Path(data_path("somepath", createdir=True))
    assert path.is_dir()
    # An existing directory is left alone.
    assert Path(data_path("somepath", createdir=True)) == path


def test_inside_project_unimportable_settings_module(no_proj_path: Path) -> None:
    with (
        set_environ(SCRAPY_SETTINGS_MODULE="tests.no_such_settings_module"),
        pytest.warns(
            UserWarning, match="Cannot import scrapy settings module tests.no_such"
        ),
    ):
        assert inside_project() is False


def test_project_data_dir_outside_project(no_proj_path: Path) -> None:
    with pytest.raises(NotConfigured, match="Not inside a project"):
        project_data_dir()


def test_project_data_dir_without_scrapy_cfg(no_proj_path: Path) -> None:
    with (
        set_environ(SCRAPY_SETTINGS_MODULE="tests.test_cmdline.settings"),
        pytest.raises(NotConfigured, match=r"Unable to find scrapy\.cfg file"),
    ):
        project_data_dir()


def test_project_data_dir_default(proj_path: Path) -> None:
    expected = (proj_path / ".scrapy").resolve()
    assert Path(project_data_dir()) == expected
    assert expected.is_dir()
    # A second call finds the directory already created.
    assert Path(project_data_dir()) == expected


def test_project_data_dir_from_scrapy_cfg(proj_path: Path) -> None:
    datadir = proj_path / "custom-datadir"
    Path("scrapy.cfg").write_text(f"[datadir]\ndefault = {datadir}\n")
    assert Path(project_data_dir()) == datadir
    assert datadir.is_dir()


class TestGetProjectSettings:
    def test_valid_envvar(self):
        value = "tests.test_cmdline.settings"
        envvars = {
            "SCRAPY_SETTINGS_MODULE": value,
        }
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

    def test_envvar_project_dir_in_sys_path(
        self, proj_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "path", sys.path.copy())
        monkeypatch.setenv("SCRAPY_SETTINGS_MODULE", "tests.test_cmdline.settings")
        get_project_settings()
        assert str(proj_path) in sys.path

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

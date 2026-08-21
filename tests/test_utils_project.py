from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import set_environ
from scrapy.utils.project import (
    data_path,
    find_projects,
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


def test_find_projects(tmp_path: Path) -> None:
    for relative_path in (
        "a/scrapy.cfg",
        "a/nested/scrapy.cfg",
        "b/c/d/scrapy.cfg",
        ".hidden/scrapy.cfg",
        "no-project/setup.py",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    assert list(find_projects(tmp_path)) == [
        tmp_path / "a",
        tmp_path / "b" / "c" / "d",
    ]


def test_find_projects_skips_virtual_environments(tmp_path: Path) -> None:
    # An arbitrarily-named directory, to show detection does not rely on it
    # being called venv or .venv.
    venv = tmp_path / "my-env"
    (venv / "lib" / "project").mkdir(parents=True)
    (venv / "pyvenv.cfg").touch()
    (venv / "lib" / "project" / "scrapy.cfg").touch()

    assert list(find_projects(tmp_path)) == []


def test_find_projects_ignored_dirs(tmp_path: Path) -> None:
    for relative_path in ("a/scrapy.cfg", "b/scrapy.cfg"):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True)
        path.touch()

    assert list(find_projects(tmp_path, ignored_dirs=["a"])) == [tmp_path / "b"]


def test_find_projects_root(tmp_path: Path) -> None:
    (tmp_path / "scrapy.cfg").touch()
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "scrapy.cfg").touch()

    assert list(find_projects(tmp_path)) == [tmp_path]


def test_find_projects_max_depth(tmp_path: Path) -> None:
    for relative_path in ("a/scrapy.cfg", "b/c/scrapy.cfg"):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True)
        path.touch()

    assert list(find_projects(tmp_path, max_depth=0)) == []
    assert list(find_projects(tmp_path, max_depth=1)) == [tmp_path / "a"]

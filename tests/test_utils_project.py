from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import set_environ
from scrapy.utils.project import data_path, get_project_settings, project_data_dir

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def proj_path(tmp_path: Path) -> Generator[Path]:
    prev_dir = Path.cwd()
    project_dir = tmp_path

    try:
        os.chdir(project_dir)
        Path("pyproject.toml").write_text("[tool.scrapy]\n", encoding="utf-8")

        yield project_dir
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


def test_project_data_dir_without_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project defined only through the environment has no folder to infer
    its data dir from."""
    monkeypatch.chdir(tmp_path)
    with (
        set_environ(SCRAPY_SETTINGS_MODULE="tests.test_cmdline.settings"),
        pytest.raises(NotConfigured, match=r"Unable to find a pyproject\.toml file"),
    ):
        project_data_dir()


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

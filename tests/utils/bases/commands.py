from __future__ import annotations

from shutil import copytree
from typing import TYPE_CHECKING, ClassVar

import pytest

from tests.utils.cmdline import call

if TYPE_CHECKING:
    from pathlib import Path


class TestProjectBase:
    """A base class for tests that may need a Scrapy project."""

    project_name: ClassVar[str] = "testproject"

    @pytest.fixture(scope="session")
    @classmethod
    def _proj_path_cached(cls, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """Create a Scrapy project in a temporary directory and return its path.

        Used as a cache for ``proj_path``.
        """
        tmp_path = tmp_path_factory.mktemp("proj")
        call("startproject", cls.project_name, cwd=tmp_path)
        return tmp_path / cls.project_name

    @pytest.fixture
    @classmethod
    def proj_path(cls, tmp_path: Path, _proj_path_cached: Path) -> Path:
        """Copy a pre-generated Scrapy project into a temporary directory and return its path."""
        proj_path = tmp_path / cls.project_name
        copytree(_proj_path_cached, proj_path)
        return proj_path

    @staticmethod
    def _append_settings(proj_mod_path: Path, text: str) -> None:
        """Add text to the end of the project settings.py."""
        with (proj_mod_path / "settings.py").open("a", encoding="utf-8") as f:
            f.write(text)

    @classmethod
    def _break_bootstrap(cls, proj_mod_path: Path) -> None:
        """Enable a spider middleware that raises an exception when built, so
        that crawling any spider of the project fails before it starts."""
        cls._append_settings(
            proj_mod_path,
            """

class BreakingMiddleware:
    def __init__(self):
        raise RuntimeError("Breaking middleware")


SPIDER_MIDDLEWARES = {f"{__name__}.BreakingMiddleware": 100}
""",
        )

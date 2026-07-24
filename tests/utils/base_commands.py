from __future__ import annotations

from shutil import copytree
from typing import TYPE_CHECKING

import pytest

from tests.utils.cmdline import call

if TYPE_CHECKING:
    from pathlib import Path


class TestProjectBase:
    """A base class for tests that may need a Scrapy project."""

    project_name = "testproject"

    @pytest.fixture(scope="session")
    def _proj_path_cached(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """Create a Scrapy project in a temporary directory and return its path.

        Used as a cache for ``proj_path``.
        """
        tmp_path = tmp_path_factory.mktemp("proj")
        call("startproject", self.project_name, cwd=tmp_path)
        return tmp_path / self.project_name

    @pytest.fixture
    def proj_path(self, tmp_path: Path, _proj_path_cached: Path) -> Path:
        """Copy a pre-generated Scrapy project into a temporary directory and return its path."""
        proj_path = tmp_path / self.project_name
        copytree(_proj_path_cached, proj_path)
        return proj_path

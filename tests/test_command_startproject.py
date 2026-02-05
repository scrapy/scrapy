from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from itertools import chain
from pathlib import Path
from shutil import copytree
from stat import S_IWRITE as ANYONE_WRITE_PERMISSION

import scrapy
from scrapy.commands.startproject import IGNORE
from scrapy.utils.test import get_testenv
from tests.utils.cmdline import call, proc


class TestStartprojectCommand:
    project_name = "testproject"

    @staticmethod
    def _assert_files_exist(project_dir: Path, project_name: str) -> None:
        assert (project_dir / "scrapy.cfg").exists()
        assert (project_dir / project_name).exists()
        assert (project_dir / project_name / "__init__.py").exists()
        assert (project_dir / project_name / "items.py").exists()
        assert (project_dir / project_name / "pipelines.py").exists()
        assert (project_dir / project_name / "settings.py").exists()
        assert (project_dir / project_name / "spiders" / "__init__.py").exists()

    def test_startproject(self, tmp_path: Path) -> None:
        # with no dir argument creates the project in the "self.project_name" subdir of cwd
        assert call("startproject", self.project_name, cwd=tmp_path) == 0
        self._assert_files_exist(tmp_path / self.project_name, self.project_name)

        assert call("startproject", self.project_name, cwd=tmp_path) == 1
        assert call("startproject", "wrong---project---name") == 1
        assert call("startproject", "sys") == 1

    def test_startproject_with_project_dir(self, tmp_path: Path) -> None:
        # with a dir arg creates the project in the specified dir
        project_dir = tmp_path / "project"
        assert (
            call("startproject", self.project_name, str(project_dir), cwd=tmp_path) == 0
        )
        self._assert_files_exist(project_dir, self.project_name)

        assert (
            call(
                "startproject", self.project_name, str(project_dir) + "2", cwd=tmp_path
            )
            == 0
        )

        assert (
            call("startproject", self.project_name, str(project_dir), cwd=tmp_path) == 1
        )
        assert (
            call(
                "startproject", self.project_name + "2", str(project_dir), cwd=tmp_path
            )
            == 1
        )
        assert call("startproject", "wrong---project---name") == 1
        assert call("startproject", "sys") == 1
        assert call("startproject") == 2
        assert (
            call("startproject", self.project_name, str(project_dir), "another_params")
            == 2
        )

    def test_existing_project_dir(self, tmp_path: Path) -> None:
        project_name = self.project_name + "_existing"
        project_path = tmp_path / project_name
        project_path.mkdir()

        assert call("startproject", project_name, cwd=tmp_path) == 0
        self._assert_files_exist(project_path, project_name)


def get_permissions_dict(
    path: str | os.PathLike, renamings=None, ignore=None
) -> dict[str, str]:
    def get_permissions(path: Path) -> str:
        return oct(path.stat().st_mode)

    path_obj = Path(path)

    renamings = renamings or ()
    permissions_dict = {
        ".": get_permissions(path_obj),
    }
    for root, dirs, files in os.walk(path_obj):
        nodes = list(chain(dirs, files))
        if ignore:
            ignored_names = ignore(root, nodes)
            nodes = [node for node in nodes if node not in ignored_names]
        for node in nodes:
            absolute_path = Path(root, node)
            relative_path = str(absolute_path.relative_to(path))
            for search_string, replacement in renamings:
                relative_path = relative_path.replace(search_string, replacement)
            permissions = get_permissions(absolute_path)
            permissions_dict[relative_path] = permissions
    return permissions_dict


class TestStartprojectTemplates:
    def test_startproject_template_override(self, tmp_path: Path) -> None:
        tmpl = tmp_path / "templates"
        tmpl_proj = tmpl / "project"
        project_name = "testproject"

        copytree(Path(scrapy.__path__[0], "templates"), tmpl)
        (tmpl_proj / "root_template").write_bytes(b"")

        args = ["--set", f"TEMPLATES_DIR={tmpl}"]
        _, out, _ = proc("startproject", project_name, *args, cwd=tmp_path)
        assert f"New Scrapy project '{project_name}', using template directory" in out
        assert str(tmpl_proj) in out
        assert (tmp_path / project_name / "root_template").exists()

    def test_startproject_permissions_from_writable(self, tmp_path: Path) -> None:
        """Check that generated files have the right permissions when the
        template folder has the same permissions as in the project, i.e.
        everything is writable."""
        scrapy_path = scrapy.__path__[0]
        project_template = Path(scrapy_path, "templates", "project")
        project_name = "startproject1"
        renamings = (
            ("module", project_name),
            (".tmpl", ""),
        )
        expected_permissions = get_permissions_dict(
            project_template,
            renamings,
            IGNORE,
        )

        destination = tmp_path / "proj"
        destination.mkdir()
        process = subprocess.Popen(
            (
                sys.executable,
                "-m",
                "scrapy.cmdline",
                "startproject",
                project_name,
            ),
            cwd=destination,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=get_testenv(),
        )
        process.wait()

        project_dir = destination / project_name
        actual_permissions = get_permissions_dict(project_dir)

        assert actual_permissions == expected_permissions

    def test_startproject_permissions_from_read_only(self, tmp_path: Path) -> None:
        """Check that generated files have the right permissions when the
        template folder has been made read-only, which is something that some
        systems do.

        See https://github.com/scrapy/scrapy/pull/4604
        """
        scrapy_path = scrapy.__path__[0]
        templates_dir = Path(scrapy_path, "templates")
        project_template = Path(templates_dir, "project")
        project_name = "startproject2"
        renamings = (
            ("module", project_name),
            (".tmpl", ""),
        )
        expected_permissions = get_permissions_dict(
            project_template,
            renamings,
            IGNORE,
        )

        def _make_read_only(path: Path):
            current_permissions = path.stat().st_mode
            path.chmod(current_permissions & ~ANYONE_WRITE_PERMISSION)

        read_only_templates_dir = tmp_path / "templates"
        copytree(templates_dir, read_only_templates_dir)

        for root, dirs, files in os.walk(read_only_templates_dir):
            for node in chain(dirs, files):
                _make_read_only(Path(root, node))

        destination = tmp_path / "proj"
        destination.mkdir()
        assert (
            call(
                "startproject",
                project_name,
                "--set",
                f"TEMPLATES_DIR={read_only_templates_dir}",
                cwd=destination,
            )
            == 0
        )

        project_dir = destination / project_name
        actual_permissions = get_permissions_dict(project_dir)

        assert actual_permissions == expected_permissions

    def test_startproject_permissions_unchanged_in_destination(
        self, tmp_path: Path
    ) -> None:
        """Check that preexisting folders and files in the destination folder
        do not see their permissions modified."""
        scrapy_path = scrapy.__path__[0]
        project_template = Path(scrapy_path, "templates", "project")
        project_name = "startproject3"
        renamings = (
            ("module", project_name),
            (".tmpl", ""),
        )
        expected_permissions = get_permissions_dict(
            project_template,
            renamings,
            IGNORE,
        )

        destination = tmp_path / "proj"
        project_dir = destination / project_name
        project_dir.mkdir(parents=True)

        existing_nodes = {
            f"{permissions:o}{extension}": permissions
            for extension in ("", ".d")
            for permissions in (
                0o444,
                0o555,
                0o644,
                0o666,
                0o755,
                0o777,
            )
        }
        for node, permissions in existing_nodes.items():
            path = project_dir / node
            if node.endswith(".d"):
                path.mkdir(mode=permissions)
            else:
                path.touch(mode=permissions)
            expected_permissions[node] = oct(path.stat().st_mode)

        assert call("startproject", project_name, ".", cwd=project_dir) == 0

        actual_permissions = get_permissions_dict(project_dir)

        assert actual_permissions == expected_permissions

    def test_startproject_permissions_umask_022(self, tmp_path: Path) -> None:
        """Check that generated files have the right permissions when the
        system uses a umask value that causes new files to have different
        permissions than those from the template folder."""

        @contextmanager
        def umask(new_mask):
            cur_mask = os.umask(new_mask)
            yield
            os.umask(cur_mask)

        scrapy_path = scrapy.__path__[0]
        project_template = Path(scrapy_path, "templates", "project")
        project_name = "umaskproject"
        renamings = (
            ("module", project_name),
            (".tmpl", ""),
        )
        expected_permissions = get_permissions_dict(
            project_template,
            renamings,
            IGNORE,
        )

        with umask(0o002):
            destination = tmp_path / "proj"
            destination.mkdir()
            assert call("startproject", project_name, cwd=destination) == 0

            project_dir = destination / project_name
            actual_permissions = get_permissions_dict(project_dir)

            assert actual_permissions == expected_permissions

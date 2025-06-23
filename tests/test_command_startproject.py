from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from itertools import chain
from pathlib import Path
from shutil import copytree
from stat import S_IWRITE as ANYONE_WRITE_PERMISSION
from tempfile import mkdtemp

import scrapy
from scrapy.commands.startproject import IGNORE
from tests.test_commands import TestProjectBase


class TestStartprojectCommand(TestProjectBase):
    def test_startproject(self):
        p, out, err = self.proc("startproject", self.project_name)
        print(out)
        print(err, file=sys.stderr)
        assert p.returncode == 0

        assert Path(self.proj_path, "scrapy.cfg").exists()
        assert Path(self.proj_path, "testproject").exists()
        assert Path(self.proj_mod_path, "__init__.py").exists()
        assert Path(self.proj_mod_path, "items.py").exists()
        assert Path(self.proj_mod_path, "pipelines.py").exists()
        assert Path(self.proj_mod_path, "settings.py").exists()
        assert Path(self.proj_mod_path, "spiders", "__init__.py").exists()

        assert self.call("startproject", self.project_name) == 1
        assert self.call("startproject", "wrong---project---name") == 1
        assert self.call("startproject", "sys") == 1

    def test_startproject_with_project_dir(self):
        project_dir = mkdtemp()
        assert self.call("startproject", self.project_name, project_dir) == 0

        assert Path(project_dir, "scrapy.cfg").exists()
        assert Path(project_dir, "testproject").exists()
        assert Path(project_dir, self.project_name, "__init__.py").exists()
        assert Path(project_dir, self.project_name, "items.py").exists()
        assert Path(project_dir, self.project_name, "pipelines.py").exists()
        assert Path(project_dir, self.project_name, "settings.py").exists()
        assert Path(project_dir, self.project_name, "spiders", "__init__.py").exists()

        assert self.call("startproject", self.project_name, project_dir + "2") == 0

        assert self.call("startproject", self.project_name, project_dir) == 1
        assert self.call("startproject", self.project_name + "2", project_dir) == 1
        assert self.call("startproject", "wrong---project---name") == 1
        assert self.call("startproject", "sys") == 1
        assert self.call("startproject") == 2
        assert (
            self.call("startproject", self.project_name, project_dir, "another_params")
            == 2
        )

    def test_existing_project_dir(self):
        project_dir = mkdtemp()
        project_name = self.project_name + "_existing"
        project_path = Path(project_dir, project_name)
        project_path.mkdir()

        p, out, err = self.proc("startproject", project_name, cwd=project_dir)
        print(out)
        print(err, file=sys.stderr)
        assert p.returncode == 0

        assert Path(project_path, "scrapy.cfg").exists()
        assert Path(project_path, project_name).exists()
        assert Path(project_path, project_name, "__init__.py").exists()
        assert Path(project_path, project_name, "items.py").exists()
        assert Path(project_path, project_name, "pipelines.py").exists()
        assert Path(project_path, project_name, "settings.py").exists()
        assert Path(project_path, project_name, "spiders", "__init__.py").exists()


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


class TestStartprojectTemplates(TestProjectBase):
    def setup_method(self):
        super().setup_method()
        self.tmpl = str(Path(self.temp_path, "templates"))
        self.tmpl_proj = str(Path(self.tmpl, "project"))

    def test_startproject_template_override(self):
        copytree(Path(scrapy.__path__[0], "templates"), self.tmpl)
        Path(self.tmpl_proj, "root_template").write_bytes(b"")
        assert Path(self.tmpl_proj, "root_template").exists()

        args = ["--set", f"TEMPLATES_DIR={self.tmpl}"]
        p, out, err = self.proc("startproject", self.project_name, *args)
        assert (
            f"New Scrapy project '{self.project_name}', using template directory" in out
        )
        assert self.tmpl_proj in out
        assert Path(self.proj_path, "root_template").exists()

    def test_startproject_permissions_from_writable(self):
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

        destination = mkdtemp()
        process = subprocess.Popen(
            (
                sys.executable,
                "-m",
                "scrapy.cmdline",
                "startproject",
                project_name,
            ),
            cwd=destination,
            env=self.env,
        )
        process.wait()

        project_dir = Path(destination, project_name)
        actual_permissions = get_permissions_dict(project_dir)

        assert actual_permissions == expected_permissions

    def test_startproject_permissions_from_read_only(self):
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

        read_only_templates_dir = str(Path(mkdtemp()) / "templates")
        copytree(templates_dir, read_only_templates_dir)

        for root, dirs, files in os.walk(read_only_templates_dir):
            for node in chain(dirs, files):
                _make_read_only(Path(root, node))

        destination = mkdtemp()
        process = subprocess.Popen(
            (
                sys.executable,
                "-m",
                "scrapy.cmdline",
                "startproject",
                project_name,
                "--set",
                f"TEMPLATES_DIR={read_only_templates_dir}",
            ),
            cwd=destination,
            env=self.env,
        )
        process.wait()

        project_dir = Path(destination, project_name)
        actual_permissions = get_permissions_dict(project_dir)

        assert actual_permissions == expected_permissions

    def test_startproject_permissions_unchanged_in_destination(self):
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

        destination = mkdtemp()
        project_dir = Path(destination, project_name)

        existing_nodes = {
            oct(permissions)[2:] + extension: permissions
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
        project_dir.mkdir()
        for node, permissions in existing_nodes.items():
            path = project_dir / node
            if node.endswith(".d"):
                path.mkdir(mode=permissions)
            else:
                path.touch(mode=permissions)
            expected_permissions[node] = oct(path.stat().st_mode)

        process = subprocess.Popen(
            (
                sys.executable,
                "-m",
                "scrapy.cmdline",
                "startproject",
                project_name,
                ".",
            ),
            cwd=project_dir,
            env=self.env,
        )
        process.wait()

        actual_permissions = get_permissions_dict(project_dir)

        assert actual_permissions == expected_permissions

    def test_startproject_permissions_umask_022(self):
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
            destination = mkdtemp()
            process = subprocess.Popen(
                (
                    sys.executable,
                    "-m",
                    "scrapy.cmdline",
                    "startproject",
                    project_name,
                ),
                cwd=destination,
                env=self.env,
            )
            process.wait()

            project_dir = Path(destination, project_name)
            actual_permissions = get_permissions_dict(project_dir)

            assert actual_permissions == expected_permissions

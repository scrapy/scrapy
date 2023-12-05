from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence

from packaging.requirements import Requirement

from tox.config.types import Command
from tox.execute.request import StdinSource
from tox.tox_env.errors import Fail, Recreate
from tox.tox_env.installer import Installer
from tox.tox_env.python.api import Python
from tox.tox_env.python.package import EditableLegacyPackage, EditablePackage, SdistPackage, WheelPackage
from tox.tox_env.python.pip.req_file import PythonDeps

if TYPE_CHECKING:
    from tox.config.main import Config
    from tox.tox_env.package import PathPackage


class Pip(Installer[Python]):
    """Pip is a python installer that can install packages as defined by PEP-508 and PEP-517."""

    def __init__(self, tox_env: Python, with_list_deps: bool = True) -> None:  # noqa: FBT001, FBT002
        self._with_list_deps = with_list_deps
        super().__init__(tox_env)

    def _register_config(self) -> None:
        self._env.conf.add_config(
            keys=["pip_pre"],
            of_type=bool,
            default=False,
            desc="install the latest available pre-release (alpha/beta/rc) of dependencies without a specified version",
        )
        self._env.conf.add_config(
            keys=["install_command"],
            of_type=Command,
            default=self.default_install_command,
            post_process=self.post_process_install_command,
            desc="command used to install packages",
        )
        self._env.conf.add_config(
            keys=["constrain_package_deps"],
            of_type=bool,
            default=False,
            desc="If true, apply constraints during install_package_deps.",
        )
        self._env.conf.add_config(
            keys=["use_frozen_constraints"],
            of_type=bool,
            default=False,
            desc="Use the exact versions of installed deps as constraints, otherwise use the listed deps.",
        )
        if self._with_list_deps:  # pragma: no branch
            self._env.conf.add_config(
                keys=["list_dependencies_command"],
                of_type=Command,
                default=Command(["python", "-m", "pip", "freeze", "--all"]),
                desc="command used to list installed packages",
            )

    def default_install_command(self, conf: Config, env_name: str | None) -> Command:  # noqa: ARG002
        isolated_flag = "-E" if self._env.base_python.version_info.major == 2 else "-I"  # noqa: PLR2004
        cmd = Command(["python", isolated_flag, "-m", "pip", "install", "{opts}", "{packages}"])
        return self.post_process_install_command(cmd)

    def post_process_install_command(self, cmd: Command) -> Command:
        install_command = cmd.args
        pip_pre: bool = self._env.conf["pip_pre"]
        try:
            opts_at = install_command.index("{opts}")
        except ValueError:
            if pip_pre:
                install_command.append("--pre")
        else:
            if pip_pre:
                install_command[opts_at] = "--pre"
            else:
                install_command.pop(opts_at)
        return cmd

    def installed(self) -> list[str]:
        cmd: Command = self._env.conf["list_dependencies_command"]
        result = self._env.execute(cmd=cmd.args, stdin=StdinSource.OFF, run_id="freeze", show=False)
        result.assert_success()
        return result.out.splitlines()

    def install(self, arguments: Any, section: str, of_type: str) -> None:
        if isinstance(arguments, PythonDeps):
            self._install_requirement_file(arguments, section, of_type)
        elif isinstance(arguments, Sequence):
            self._install_list_of_deps(arguments, section, of_type)
        else:
            logging.warning("pip cannot install %r", arguments)
            raise SystemExit(1)

    def constraints_file(self) -> Path:
        return Path(self._env.env_dir) / "constraints.txt"

    @property
    def constrain_package_deps(self) -> bool:
        return bool(self._env.conf["constrain_package_deps"])

    @property
    def use_frozen_constraints(self) -> bool:
        return bool(self._env.conf["use_frozen_constraints"])

    def _install_requirement_file(self, arguments: PythonDeps, section: str, of_type: str) -> None:
        try:
            new_options, new_reqs = arguments.unroll()
        except ValueError as exception:
            msg = f"{exception} for tox env py within deps"
            raise Fail(msg) from exception
        new_requirements: list[str] = []
        new_constraints: list[str] = []
        for req in new_reqs:
            (new_constraints if req.startswith("-c ") else new_requirements).append(req)
        constraint_options = {
            "constrain_package_deps": self.constrain_package_deps,
            "use_frozen_constraints": self.use_frozen_constraints,
        }
        new = {
            "options": new_options,
            "requirements": new_requirements,
            "constraints": new_constraints,
            "constraint_options": constraint_options,
        }
        # if option or constraint change in any way recreate, if the requirements change only if some are removed
        with self._env.cache.compare(new, section, of_type) as (eq, old):
            if not eq:  # pragma: no branch
                if old is not None:
                    self._recreate_if_diff("install flag(s)", new_options, old["options"], lambda i: i)
                    self._recreate_if_diff("constraint(s)", new_constraints, old["constraints"], lambda i: i[3:])
                    missing_requirement = set(old["requirements"]) - set(new_requirements)
                    if missing_requirement:
                        msg = f"requirements removed: {' '.join(missing_requirement)}"
                        raise Recreate(msg)
                    old_constraint_options = old.get("constraint_options")
                    if old_constraint_options != constraint_options:
                        msg = f"constraint options changed: old={old_constraint_options} new={constraint_options}"
                        raise Recreate(msg)
                args = arguments.as_root_args
                if args:  # pragma: no branch
                    self._execute_installer(args, of_type)
                    if self.constrain_package_deps and not self.use_frozen_constraints:
                        combined_constraints = new_requirements + [c.lstrip("-c ") for c in new_constraints]
                        self.constraints_file().write_text("\n".join(combined_constraints))

    @staticmethod
    def _recreate_if_diff(of_type: str, new_opts: list[str], old_opts: list[str], fmt: Callable[[str], str]) -> None:
        if old_opts == new_opts:
            return
        removed_opts = set(old_opts) - set(new_opts)
        removed = f" removed {', '.join(sorted(fmt(i) for i in removed_opts))}" if removed_opts else ""
        added_opts = set(new_opts) - set(old_opts)
        added = f" added {', '.join(sorted(fmt(i) for i in added_opts))}" if added_opts else ""
        msg = f"changed {of_type}{removed}{added}"
        raise Recreate(msg)

    def _install_list_of_deps(  # noqa: C901
        self,
        arguments: Sequence[
            Requirement | WheelPackage | SdistPackage | EditableLegacyPackage | EditablePackage | PathPackage
        ],
        section: str,
        of_type: str,
    ) -> None:
        groups: dict[str, list[str]] = defaultdict(list)
        for arg in arguments:
            if isinstance(arg, Requirement):
                groups["req"].append(str(arg))
            elif isinstance(arg, (WheelPackage, SdistPackage, EditablePackage)):
                groups["req"].extend(str(i) for i in arg.deps)
                groups["pkg"].append(str(arg.path))
            elif isinstance(arg, EditableLegacyPackage):
                groups["req"].extend(str(i) for i in arg.deps)
                groups["dev_pkg"].append(str(arg.path))
            else:
                logging.warning("pip cannot install %r", arg)
                raise SystemExit(1)
        req_of_type = f"{of_type}_deps" if groups["pkg"] or groups["dev_pkg"] else of_type
        for value in groups.values():
            value.sort()
        with self._env.cache.compare(groups["req"], section, req_of_type) as (eq, old):
            if not eq:  # pragma: no branch
                miss = sorted(set(old or []) - set(groups["req"]))
                if miss:  # no way yet to know what to uninstall here (transitive dependencies?)
                    msg = f"dependencies removed: {', '.join(str(i) for i in miss)}"
                    raise Recreate(msg)  # pragma: no branch
                new_deps = sorted(set(groups["req"]) - set(old or []))
                if new_deps:  # pragma: no branch
                    self._execute_installer(new_deps, req_of_type)
        install_args = ["--force-reinstall", "--no-deps"]
        if groups["pkg"]:
            self._execute_installer(install_args + groups["pkg"], of_type)
        if groups["dev_pkg"]:
            for entry in groups["dev_pkg"]:
                install_args.extend(("-e", str(entry)))
            self._execute_installer(install_args, of_type)

    def _execute_installer(self, deps: Sequence[Any], of_type: str) -> None:
        if of_type == "package_deps" and self.constrain_package_deps:
            constraints_file = self.constraints_file()
            if constraints_file.exists():
                deps = [*deps, f"-c{constraints_file}"]

        cmd = self.build_install_cmd(deps)
        outcome = self._env.execute(cmd, stdin=StdinSource.OFF, run_id=f"install_{of_type}")
        outcome.assert_success()

        if of_type == "deps" and self.constrain_package_deps and self.use_frozen_constraints:
            # freeze installed deps for use as constraints
            self.constraints_file().write_text("\n".join(self.installed()))

    def build_install_cmd(self, args: Sequence[str]) -> list[str]:
        try:
            cmd: Command = self._env.conf["install_command"]
        except ValueError as exc:
            msg = f"unable to determine pip install command: {exc!s}"
            raise Fail(msg) from exc
        install_command = cmd.args
        try:
            opts_at = install_command.index("{packages}")
        except ValueError:
            opts_at = len(install_command)
        return install_command[:opts_at] + list(args) + install_command[opts_at + 1 :]


__all__ = ("Pip",)

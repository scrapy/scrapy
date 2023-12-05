from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from tox.config.sets import CoreConfigSet, EnvConfigSet


def add_change_dir_conf(config: EnvConfigSet, core: CoreConfigSet) -> None:
    def _post_process_change_dir(value: Path) -> Path:
        if not value.is_absolute():
            value = (core["tox_root"] / value).resolve()
        return value

    config.add_config(
        keys=["change_dir", "changedir"],
        of_type=Path,
        default=lambda conf, name: cast(Path, conf.core["tox_root"]),  # noqa: ARG005
        desc="change to this working directory when executing the test command",
        post_process=_post_process_change_dir,
    )


__all__ = [
    "add_change_dir_conf",
]

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Optional, Set, cast

from packaging.markers import Marker, Op, Variable  # type: ignore[attr-defined]

if TYPE_CHECKING:
    from packaging.requirements import Requirement


def dependencies_with_extras(deps: list[Requirement], extras: set[str], package_name: str) -> list[Requirement]:
    return dependencies_with_extras_from_markers(extract_extra_markers(deps), extras, package_name)


def dependencies_with_extras_from_markers(
    deps_with_markers: list[tuple[Requirement, set[str | None]]],
    extras: set[str],
    package_name: str,
) -> list[Requirement]:
    result: list[Requirement] = []
    found: set[str] = set()
    todo: set[str | None] = extras | {None}
    visited: set[str | None] = set()
    while todo:
        new_extras: set[str | None] = set()
        for req, extra_markers in deps_with_markers:
            if todo & extra_markers:
                if req.name == package_name:  # support for recursive extras
                    new_extras.update(req.extras or set())
                else:
                    req_str = str(req)
                    if req_str not in found:
                        found.add(req_str)
                        result.append(req)
        visited.update(todo)
        todo = new_extras - visited
    return result


def extract_extra_markers(deps: list[Requirement]) -> list[tuple[Requirement, set[str | None]]]:
    """
    Extract extra markers from dependencies.

    :param deps: the dependencies
    :return: a list of requirement, extras set
    """
    return [_extract_extra_markers(d) for d in deps]


def _extract_extra_markers(req: Requirement) -> tuple[Requirement, set[str | None]]:
    req = deepcopy(req)
    markers: list[str | tuple[Variable, Op, Variable]] = getattr(req.marker, "_markers", []) or []
    new_markers: list[str | tuple[Variable, Op, Variable]] = []
    extra_markers: set[str] = set()  # markers that have a key of extra
    marker = markers.pop(0) if markers else None
    while marker:
        extra = _get_extra(marker)
        if extra is not None:
            extra_markers.add(extra)
            if new_markers and new_markers[-1] in ("and", "or"):
                del new_markers[-1]
            marker = markers.pop(0) if markers else None
            if marker in ("and", "or"):
                marker = markers.pop(0) if markers else None
        else:
            new_markers.append(marker)
            marker = markers.pop(0) if markers else None
    if new_markers:
        cast(Marker, req.marker)._markers = new_markers  # noqa: SLF001
    else:
        req.marker = None
    return req, cast(Set[Optional[str]], extra_markers) or {None}


def _get_extra(_marker: str | tuple[Variable, Op, Variable]) -> str | None:
    if (
        isinstance(_marker, tuple)
        and len(_marker) == 3  # noqa: PLR2004
        and _marker[0].value == "extra"
        and _marker[1].value == "=="
    ):
        return _marker[2].value
    return None

from __future__ import annotations

from typing import Literal, cast

StopMode = Literal["graceful", "fast", "force"]

_STOP_MODE_PRIORITY: dict[StopMode, int] = {
    "graceful": 0,
    "fast": 1,
    "force": 2,
}


def normalize_stop_mode(mode: StopMode | None, *, allow_force: bool = True) -> StopMode:
    if mode is None:
        return "graceful"
    if mode not in _STOP_MODE_PRIORITY:
        raise ValueError(
            f"Unknown stop mode {mode!r}. Expected one of: graceful, fast, force"
        )
    normalized = cast("StopMode", mode)
    if normalized == "force" and not allow_force:
        raise ValueError("The force stop mode is not supported in this context")
    return normalized


def max_stop_mode(mode1: StopMode, mode2: StopMode) -> StopMode:
    if _STOP_MODE_PRIORITY[mode1] >= _STOP_MODE_PRIORITY[mode2]:
        return mode1
    return mode2

from __future__ import annotations

from typing import Literal

_StopMode = Literal["graceful", "fast", "force"]

_STOP_MODE_PRIORITY: dict[_StopMode, int] = {
    "graceful": 0,
    "fast": 1,
    "force": 2,
}


def _normalize_stop_mode(mode: _StopMode, *, allow_force: bool = True) -> _StopMode:
    if mode not in _STOP_MODE_PRIORITY:
        raise ValueError(
            f"Unknown stop mode {mode!r}. Expected one of: graceful, fast, force"
        )
    if mode == "force" and not allow_force:
        raise ValueError("The force stop mode is not supported in this context")
    return mode


def max_stop_mode(mode1: _StopMode, mode2: _StopMode) -> _StopMode:
    if _STOP_MODE_PRIORITY[mode1] >= _STOP_MODE_PRIORITY[mode2]:
        return mode1
    return mode2

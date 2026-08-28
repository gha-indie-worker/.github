from __future__ import annotations

from typing import Iterable


def has_write_permission(values: Iterable[tuple[int, str, str]]) -> bool:
    for _line, permission, value in values:
        if permission.lower() == "write-all" or value.lower() in {"write", "write-all"}:
            return True
    return False

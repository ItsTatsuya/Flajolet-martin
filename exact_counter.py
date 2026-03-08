from __future__ import annotations

import sys


def deep_sizeof(obj: object, seen: set[int] | None = None) -> int:
    if seen is None:
        seen = set()

    obj_id = id(obj)
    if obj_id in seen:
        return 0
    seen.add(obj_id)

    size = sys.getsizeof(obj)

    if isinstance(obj, dict):
        for key, value in obj.items():
            size += deep_sizeof(key, seen)
            size += deep_sizeof(value, seen)
        return size

    if isinstance(obj, (list, tuple, set, frozenset)):
        for item in obj:
            size += deep_sizeof(item, seen)
        return size

    if isinstance(obj, (str, bytes, bytearray)):
        return size

    if hasattr(obj, "__dict__"):
        size += deep_sizeof(vars(obj), seen)

    return size


class ExactDistinctCounter:
    def __init__(self) -> None:
        self.seen_ips: set[str] = set()

    def process(self, ip: str) -> None:
        self.seen_ips.add(ip)

    def distinct_count(self) -> int:
        return len(self.seen_ips)

    def memory_bytes(self) -> int:
        return deep_sizeof(self.seen_ips)

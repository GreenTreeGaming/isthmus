"""Turn engine/assumptions.py into the Assumptions tab's JSON: grouped by its `# ---- section`
headers, with each constant's comments as the note. Values are made JSON-safe (dict keys may be tuples)."""
from __future__ import annotations

import inspect
import re
from types import ModuleType
from typing import Any

UNITS = [("_VPH", "veh/h/lane"), ("_KPH", "km/h"), ("_MPS", "m/s"), ("_S", "s"), ("_M", "m")]
SECTION = re.compile(r"^#\s*-{3,}\s*(.+?)\s*$")
CONST = re.compile(r"^([A-Z][A-Z0-9_]*)\s*(?::[^=]+)?=\s*(.*)$")


def _key(k: Any) -> str:
    return " / ".join(map(str, k)) if isinstance(k, tuple) else str(k)


def json_safe(v: Any) -> Any:
    """Recursively convert to JSON-serializable values: tuple dict keys -> 'a / b / c', sets/tuples -> lists."""
    if isinstance(v, dict):
        return {_key(k): json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set, frozenset)):
        items = sorted(v) if isinstance(v, (set, frozenset)) else v
        return [json_safe(x) for x in items]
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    return str(v)


def _display(v: Any) -> str | int | float | bool:
    if isinstance(v, (int, float, str, bool)):
        return v
    if isinstance(v, dict):
        return " · ".join(f"{_key(k)}: {', '.join(map(str, x)) if isinstance(x, (tuple, list)) else x}" for k, x in v.items())
    if isinstance(v, (list, tuple, set, frozenset)):
        return ", ".join(map(str, sorted(v) if isinstance(v, (set, frozenset)) else v))
    return str(v)


def _pretty(name: str) -> tuple[str, str | None]:
    unit = None
    for suffix, u in UNITS:
        if name.endswith(suffix):
            name, unit = name[: -len(suffix)], u
            break
    words = name.replace("_", " ").lower()
    return words[:1].upper() + words[1:], unit


def describe(module: ModuleType) -> list[dict[str, Any]]:
    try:
        lines = inspect.getsource(module).splitlines()
    except (OSError, TypeError):
        lines = []
    groups: list[dict[str, Any]] = []
    current = {"title": "General", "items": []}
    pending: list[str] = []
    seen: set[str] = set()
    for line in lines:
        s = line.strip()
        m = SECTION.match(s)
        if m:
            if current["items"]:
                groups.append(current)
            current = {"title": m.group(1).capitalize(), "items": []}
            pending = []
            continue
        if s.startswith("#"):
            pending.append(s.lstrip("# ").strip())
            continue
        if not s:
            pending = []
            continue
        c = CONST.match(line)  # top level only (no indentation)
        if c and hasattr(module, c.group(1)):
            name = c.group(1)
            trailing = c.group(2).split("#", 1)[1].strip() if "#" in c.group(2) else ""
            note = " ".join(pending + ([trailing] if trailing else [])) or None
            label, unit = _pretty(name)
            current["items"].append({"name": label, "key": name, "value": _display(getattr(module, name)),
                                     "unit": unit, "note": note})
            seen.add(name)
            pending = []
    if current["items"]:
        groups.append(current)
    # anything defined without a parsable line (e.g. computed) still shows up
    rest = [k for k in vars(module) if k.isupper() and k not in seen]
    if rest:
        groups.append({"title": "Other", "items": [
            {"name": _pretty(k)[0], "key": k, "value": _display(getattr(module, k)), "unit": _pretty(k)[1]} for k in rest]})
    return json_safe(groups)

from __future__ import annotations

import re
from pathlib import Path

from .errors import InvalidInputError


_WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_SECRET_PATTERNS = (
    re.compile(r"(?i)(app[_-]?secret|access[_-]?token|cookie)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)authorization:\s*bearer\s+[^\s]+"),
)


def sanitize_category(value: str | None, *, default: str = "待分类") -> str:
    raw = (value or default).strip()
    if not raw:
        raw = default
    if Path(raw).is_absolute() or re.match(r"^[A-Za-z]:", raw) or raw.startswith(("\\\\", "//")):
        raise InvalidInputError("分类目录必须是素材库下的相对目录名。")
    if any(part in {".", ".."} for part in re.split(r"[\\/]", raw)):
        raise InvalidInputError("分类目录不能包含 . 或 .. 路径段。")
    cleaned = _WINDOWS_INVALID.sub("_", raw).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        raise InvalidInputError("分类目录清理后为空。")
    if cleaned.upper() in _WINDOWS_RESERVED:
        raise InvalidInputError(f"分类目录 {cleaned!r} 是 Windows 保留名称。")
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip(" .")
    return cleaned


def safe_child(root: Path, *parts: str) -> Path:
    resolved_root = root.expanduser().resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise InvalidInputError("目标路径越过了素材库根目录。") from exc
    return candidate


def redact(text: str) -> str:
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(lambda match: match.group(0).split(":")[0].split("=")[0] + "=[REDACTED]", result)
    return result


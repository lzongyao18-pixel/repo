from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import LocalizationError
from .models import write_json_atomic


REQUIRED_LOCALIZATION_FIELDS = (
    "caption_zh_localized",
    "transcript_zh_localized",
)


def create_localization_request(
    output_path: Path,
    *,
    video_id: str,
    caption: str,
    transcript: str,
    source_language: str | None,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "video_id": video_id,
        "source_language": source_language,
        "caption": caption,
        "transcript": transcript,
        "required_output_fields": list(REQUIRED_LOCALIZATION_FIELDS),
        "policy": "Read references/localization-policy.md before producing the output.",
    }
    write_json_atomic(output_path, payload)
    return payload


def apply_localization(input_path: Path, output_path: Path, *, expected_video_id: str) -> dict[str, Any]:
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalizationError("本土化结果文件不可读或不是有效 JSON。") from exc
    if str(payload.get("video_id")) != expected_video_id:
        raise LocalizationError("本土化结果中的 Video ID 与任务不一致。")
    missing = [key for key in REQUIRED_LOCALIZATION_FIELDS if not isinstance(payload.get(key), str)]
    if missing:
        raise LocalizationError("本土化结果缺少字符串字段：" + ", ".join(missing))
    normalized = {
        "schema_version": 1,
        "video_id": expected_video_id,
        **{key: payload[key].strip() for key in REQUIRED_LOCALIZATION_FIELDS},
        "provider": str(payload.get("provider") or "codex"),
        "model": str(payload.get("model") or "codex-current"),
        "prompt_version": str(payload.get("prompt_version") or "v1"),
    }
    write_json_atomic(output_path, normalized)
    return normalized

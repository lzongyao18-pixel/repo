from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class VideoJob:
    platform: str
    video_id: str
    source_url: str
    canonical_url: str | None = None
    category: str = "待分类"
    creator: str | None = None
    publish_time: str | None = None
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    duration: float | None = None
    language: str | None = None
    local_folder: str | None = None
    local_video_path: str | None = None
    metadata_path: str | None = None
    transcript_path: str | None = None
    localization_path: str | None = None
    remote_record_id: str | None = None
    overall_status: str = "RECEIVED"
    download_status: str = "PENDING"
    transcription_status: str = "PENDING"
    localization_status: str = "PENDING"
    sync_status: str = "PENDING"
    last_completed_stage: str | None = None
    retry_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @property
    def key(self) -> tuple[str, str]:
        return self.platform, self.video_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: Any) -> "VideoJob":
        data = dict(row)
        data["hashtags"] = json.loads(data.pop("hashtags_json") or "[]")
        return cls(**data)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


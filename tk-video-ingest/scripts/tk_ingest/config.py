from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigurationError


DEFAULT_FIELD_MAP = {
    "video_id": "Video ID",
    "video_cover": "Video Cover",
    "source_url": "Source URL",
    "creator": "Creator",
    "publish_time": "Publish Time",
    "caption": "Caption",
    "hashtags": "Hashtags",
    "transcript": "Transcript",
    "caption_zh_localized": "Caption ZH Localized",
    "transcript_zh_localized": "Transcript ZH Localized",
    "relative_path": "Relative Path",
    "machine_id": "Machine ID",
    "duration": "Duration",
    "processing_status": "Processing Status",
    "error_message": "Error Message",
}


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(slots=True)
class Settings:
    library_root: Path
    default_category: str = "待分类"
    state_db: Path | None = None
    machine_id: str = "workstation-01"
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    whisper_language: str | None = None
    whisper_cache_dir: Path | None = None
    cookie_file: Path | None = None
    cookies_from_browser: str | None = None
    ffmpeg_location: str | None = None
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_app_token: str | None = None
    feishu_table_id: str | None = None
    feishu_field_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_FIELD_MAP))

    def __post_init__(self) -> None:
        self.library_root = self.library_root.expanduser().resolve()
        self.state_db = (self.state_db or self.library_root / ".system" / "tk_ingest.db").expanduser().resolve()
        if self.whisper_cache_dir is None:
            self.whisper_cache_dir = self.library_root / ".models"

    @property
    def feishu_configured(self) -> bool:
        return all((self.feishu_app_id, self.feishu_app_secret, self.feishu_app_token, self.feishu_table_id))

    @classmethod
    def load(cls, env_file: Path | None = None) -> "Settings":
        env_path = env_file or Path.cwd() / ".env"
        file_values = _load_env_file(env_path)

        def get(name: str, default: str | None = None) -> str | None:
            return os.environ.get(name, file_values.get(name, default))

        library_root = get("TK_LIBRARY_ROOT", r"D:\TK素材库")
        if not library_root:
            raise ConfigurationError("缺少 TK_LIBRARY_ROOT。")
        state_db = get("TK_STATE_DB")
        cache_dir = get("WHISPER_CACHE_DIR")
        cookie_file = get("YTDLP_COOKIE_FILE")
        field_map = dict(DEFAULT_FIELD_MAP)
        raw_map = get("FEISHU_FIELD_MAP_JSON")
        if raw_map:
            try:
                field_map.update(json.loads(raw_map))
            except json.JSONDecodeError as exc:
                raise ConfigurationError("FEISHU_FIELD_MAP_JSON 不是有效 JSON。") from exc
        return cls(
            library_root=Path(library_root),
            default_category=get("TK_DEFAULT_CATEGORY", "待分类") or "待分类",
            state_db=Path(state_db) if state_db else None,
            machine_id=get("TK_MACHINE_ID", "workstation-01") or "workstation-01",
            whisper_model=get("WHISPER_MODEL", "small") or "small",
            whisper_device=get("WHISPER_DEVICE", "auto") or "auto",
            whisper_compute_type=get("WHISPER_COMPUTE_TYPE", "auto") or "auto",
            whisper_language=get("WHISPER_LANGUAGE") or None,
            whisper_cache_dir=Path(cache_dir) if cache_dir else None,
            cookie_file=Path(cookie_file) if cookie_file else None,
            cookies_from_browser=get("YTDLP_COOKIES_FROM_BROWSER") or None,
            ffmpeg_location=get("FFMPEG_LOCATION") or None,
            feishu_app_id=get("FEISHU_APP_ID") or None,
            feishu_app_secret=get("FEISHU_APP_SECRET") or None,
            feishu_app_token=get("FEISHU_BITABLE_APP_TOKEN") or None,
            feishu_table_id=get("FEISHU_TABLE_ID") or None,
            feishu_field_map=field_map,
        )

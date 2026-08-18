from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import VideoJob, utc_now


_COLUMNS = (
    "platform", "video_id", "source_url", "canonical_url", "category", "creator",
    "publish_time", "caption", "hashtags_json", "duration", "language", "local_folder",
    "local_video_path", "metadata_path", "transcript_path", "localization_path",
    "remote_record_id", "overall_status", "download_status", "transcription_status",
    "localization_status", "sync_status", "last_completed_stage", "retry_count",
    "error_code", "error_message", "created_at", "updated_at",
)


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._initialize()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS videos (
                platform TEXT NOT NULL,
                video_id TEXT NOT NULL,
                source_url TEXT NOT NULL,
                canonical_url TEXT,
                category TEXT NOT NULL,
                creator TEXT,
                publish_time TEXT,
                caption TEXT NOT NULL DEFAULT '',
                hashtags_json TEXT NOT NULL DEFAULT '[]',
                duration REAL,
                language TEXT,
                local_folder TEXT,
                local_video_path TEXT,
                metadata_path TEXT,
                transcript_path TEXT,
                localization_path TEXT,
                remote_record_id TEXT,
                overall_status TEXT NOT NULL,
                download_status TEXT NOT NULL,
                transcription_status TEXT NOT NULL,
                localization_status TEXT NOT NULL,
                sync_status TEXT NOT NULL,
                last_completed_stage TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (platform, video_id)
            );
            CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(overall_status, updated_at);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get(self, platform: str, video_id: str) -> VideoJob | None:
        row = self.connection.execute(
            "SELECT * FROM videos WHERE platform=? AND video_id=?", (platform, video_id)
        ).fetchone()
        return VideoJob.from_row(row) if row else None

    def save(self, job: VideoJob) -> VideoJob:
        job.updated_at = utc_now()
        values = job.to_dict()
        values["hashtags_json"] = json.dumps(values.pop("hashtags"), ensure_ascii=False)
        placeholders = ", ".join("?" for _ in _COLUMNS)
        updates = ", ".join(f"{name}=excluded.{name}" for name in _COLUMNS if name not in {"platform", "video_id", "created_at"})
        self.connection.execute(
            f"INSERT INTO videos ({', '.join(_COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(platform, video_id) DO UPDATE SET {updates}",
            tuple(values[name] for name in _COLUMNS),
        )
        self.connection.commit()
        return job

    def list_pending(self) -> list[VideoJob]:
        rows = self.connection.execute(
            "SELECT * FROM videos WHERE overall_status NOT IN ('SYNCED', 'DUPLICATE') ORDER BY updated_at"
        ).fetchall()
        return [VideoJob.from_row(row) for row in rows]


from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import Settings
from .errors import ConfigurationError, RemoteSyncError
from .models import VideoJob


BASE_URL = "https://open.feishu.cn/open-apis"
CHINA_TIMEZONE = timezone(timedelta(hours=8))
MAX_FEISHU_MEDIA_BYTES = 20 * 1024 * 1024


def format_publish_date(value: str | int | float | None) -> str:
    """Normalize TikTok publish times to YYYY-MM-DD in China Standard Time."""
    if value is None or value == "":
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    if len(raw) == 8 and raw.isdigit():
        try:
            return datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            return raw
    try:
        timestamp = float(raw)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, CHINA_TIMEZONE).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(CHINA_TIMEZONE)
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return raw


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None, token: str | None = None) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RemoteSyncError(f"飞书接口返回 HTTP {exc.code}。", detail=detail) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RemoteSyncError("无法连接或解析飞书接口响应。", detail=str(exc)) from exc
    if result.get("code", 0) != 0:
        raise RemoteSyncError(f"飞书接口错误：{result.get('msg') or result.get('message') or result.get('code')}")
    return result


def _encode_multipart(
    fields: dict[str, str],
    *,
    file_field: str,
    file_path: Path,
    boundary: str | None = None,
) -> tuple[bytes, str]:
    boundary = boundary or f"codex-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode(),
        b"Content-Type: image/jpeg\r\n\r\n",
        file_path.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _request_multipart(url: str, fields: dict[str, str], file_path: Path, token: str) -> dict[str, Any]:
    body, content_type = _encode_multipart(fields, file_field="file", file_path=file_path)
    request = Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RemoteSyncError(f"飞书素材上传返回 HTTP {exc.code}。", detail=detail) from exc
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise RemoteSyncError("无法上传或解析飞书封面素材。", detail=str(exc)) from exc
    if result.get("code", 0) != 0:
        raise RemoteSyncError(f"飞书素材上传错误：{result.get('msg') or result.get('message') or result.get('code')}")
    return result


@dataclass(slots=True)
class FeishuClient:
    settings: Settings
    _token: str | None = None

    def __post_init__(self) -> None:
        if not self.settings.feishu_configured:
            raise ConfigurationError("飞书尚未配置完整；请先创建应用和多维表格。")

    def token(self) -> str:
        if self._token:
            return self._token
        result = _request_json(
            "POST",
            f"{BASE_URL}/auth/v3/tenant_access_token/internal",
            {"app_id": self.settings.feishu_app_id, "app_secret": self.settings.feishu_app_secret},
        )
        self._token = str(result["tenant_access_token"])
        return self._token

    @property
    def records_url(self) -> str:
        return (
            f"{BASE_URL}/bitable/v1/apps/{quote(str(self.settings.feishu_app_token), safe='')}"
            f"/tables/{quote(str(self.settings.feishu_table_id), safe='')}/records"
        )

    def search_video_id(self, video_id: str) -> list[dict[str, Any]]:
        field = self.settings.feishu_field_map["video_id"]
        result = _request_json(
            "POST",
            self.records_url + "/search?page_size=20",
            {"filter": {"conjunction": "and", "conditions": [{"field_name": field, "operator": "is", "value": [video_id]}]}},
            self.token(),
        )
        return list(result.get("data", {}).get("items") or [])

    def upload_cover(self, cover_path: Path) -> str:
        if not cover_path.exists() or cover_path.stat().st_size == 0:
            raise RemoteSyncError("本地视频封面不存在或为空。")
        if cover_path.stat().st_size > MAX_FEISHU_MEDIA_BYTES:
            raise RemoteSyncError("视频封面超过飞书 20 MB 素材上传限制。")
        result = _request_multipart(
            f"{BASE_URL}/drive/v1/medias/upload_all",
            {
                "file_name": cover_path.name,
                "parent_type": "bitable_image",
                "parent_node": str(self.settings.feishu_app_token),
                "size": str(cover_path.stat().st_size),
            },
            cover_path,
            self.token(),
        )
        file_token = str(result.get("data", {}).get("file_token") or "")
        if not file_token:
            raise RemoteSyncError("飞书素材上传成功但未返回 file_token。")
        return file_token

    def upsert(self, job: VideoJob, fields: dict[str, Any], *, cover_path: Path | None = None) -> str:
        matches = self.search_video_id(job.video_id)
        if len(matches) > 1:
            raise RemoteSyncError("飞书存在多个相同 Video ID 的记录，请先清理重复行。")
        cover_field = self.settings.feishu_field_map["video_cover"]
        existing_cover = (matches[0].get("fields") or {}).get(cover_field) if matches else None
        if cover_path and not existing_cover:
            fields[cover_field] = [{"file_token": self.upload_cover(cover_path)}]
        record_id = job.remote_record_id or (matches[0].get("record_id") if matches else None)
        if record_id:
            result = _request_json("PUT", f"{self.records_url}/{quote(str(record_id), safe='')}", {"fields": fields}, self.token())
        else:
            result = _request_json("POST", self.records_url, {"fields": fields}, self.token())
        return str(result.get("data", {}).get("record", {}).get("record_id") or record_id or "")


def build_fields(settings: Settings, job: VideoJob) -> dict[str, Any]:
    transcript: dict[str, Any] = {}
    localized: dict[str, Any] = {}
    if job.transcript_path and Path(job.transcript_path).exists():
        transcript = json.loads(Path(job.transcript_path).read_text(encoding="utf-8"))
    if job.localization_path and Path(job.localization_path).exists():
        localized = json.loads(Path(job.localization_path).read_text(encoding="utf-8"))
    relative_path = ""
    if job.local_video_path:
        try:
            relative_path = str(Path(job.local_video_path).resolve().relative_to(settings.library_root))
        except ValueError:
            relative_path = ""
    values = {
        "video_id": job.video_id,
        "source_url": job.canonical_url or job.source_url,
        "creator": job.creator or "",
        "publish_time": format_publish_date(job.publish_time),
        "caption": job.caption,
        "hashtags": " ".join(f"#{tag}" for tag in job.hashtags),
        "transcript": transcript.get("text", ""),
        "caption_zh_localized": localized.get("caption_zh_localized", ""),
        "transcript_zh_localized": localized.get("transcript_zh_localized", ""),
        "relative_path": relative_path,
        "machine_id": settings.machine_id,
        "duration": job.duration or 0,
        "processing_status": job.overall_status,
        "error_message": job.error_message or "",
    }
    return {settings.feishu_field_map[key]: value for key, value in values.items()}

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Settings
from .downloader import create_video_cover, download_video, probe_video, repair_audio_download
from .errors import IngestError, RemoteSyncError
from .feishu import FeishuClient, build_fields
from .localizer import apply_localization, create_localization_request
from .models import VideoJob
from .parser import extract_video_id, validate_tiktok_url
from .security import redact, sanitize_category
from .state import StateStore
from .transcriber import transcribe_video


def _error_job(store: StateStore, job: VideoJob, error: IngestError, stage: str) -> None:
    job.overall_status = f"FAILED_{stage}"
    job.error_code = error.code
    job.error_message = redact(error.message)
    job.retry_count += 1
    if stage == "DOWNLOAD":
        job.download_status = "FAILED"
    elif stage == "TRANSCRIPTION":
        job.transcription_status = "FAILED"
    elif stage == "LOCALIZATION":
        job.localization_status = "FAILED"
    elif stage == "SYNC":
        job.sync_status = "FAILED"
    store.save(job)


def _job_result(job: VideoJob, **extra: Any) -> dict[str, Any]:
    result = {
        "status": job.overall_status,
        "platform": job.platform,
        "video_id": job.video_id,
        "category": job.category,
        "video_path": job.local_video_path,
        "download_status": job.download_status,
        "transcription_status": job.transcription_status,
        "localization_status": job.localization_status,
        "sync_status": job.sync_status,
    }
    result.update(extra)
    return result


def ingest(
    settings: Settings,
    *,
    url: str,
    category: str | None = None,
    skip_transcription: bool = False,
) -> dict[str, Any]:
    safe_url = validate_tiktok_url(url)
    safe_category = sanitize_category(category, default=settings.default_category)
    with StateStore(settings.state_db) as store:
        direct_id = extract_video_id(safe_url)
        existing = store.get("tiktok", direct_id) if direct_id else None
        info: dict[str, Any] | None = None
        if not existing:
            info = probe_video(settings, safe_url)
            video_id = str(info["id"])
            existing = store.get("tiktok", video_id)
        if existing and existing.sync_status == "SUCCESS" and existing.local_video_path and Path(existing.local_video_path).exists():
            result = _job_result(existing, message="该 Video ID 已收录，未重复下载。")
            result["status"] = "DUPLICATE"
            return result
        if (
            existing
            and existing.download_status == "SUCCESS"
            and existing.localization_status == "SUCCESS"
            and existing.local_video_path
            and Path(existing.local_video_path).exists()
            and existing.localization_path
            and Path(existing.localization_path).exists()
        ):
            result = _job_result(existing, next_action="本土化已完成；运行 sync 重试或完成飞书同步。")
            result["status"] = "PENDING_SYNC"
            return result

        job = existing
        if not job or job.download_status != "SUCCESS" or not job.local_video_path or not Path(job.local_video_path).exists():
            placeholder_id = direct_id or str((info or {}).get("id") or "pending")
            job = job or VideoJob(platform="tiktok", video_id=placeholder_id, source_url=safe_url, category=safe_category)
            try:
                downloaded, _ = download_video(settings, safe_url, safe_category, probed_info=info)
                if existing:
                    downloaded.created_at = existing.created_at
                    downloaded.retry_count = existing.retry_count
                    downloaded.remote_record_id = existing.remote_record_id
                job = store.save(downloaded)
            except IngestError as exc:
                if placeholder_id != "pending":
                    _error_job(store, job, exc, "DOWNLOAD")
                raise

        transcript_path = Path(job.local_folder) / "transcript.json"
        if skip_transcription:
            transcript = {"text": "", "language": None, "note": "转写被显式跳过"}
            job.transcription_status = "SKIPPED"
        elif job.transcription_status == "SUCCESS" and transcript_path.exists():
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        else:
            try:
                transcript = transcribe_video(settings, Path(job.local_video_path), transcript_path)
                job.transcript_path = str(transcript_path)
                job.language = transcript.get("language")
                job.transcription_status = "SUCCESS" if transcript.get("text") else "NO_SPEECH"
                job.overall_status = "TRANSCRIBED"
                job.last_completed_stage = "TRANSCRIPTION"
                job.error_code = None
                job.error_message = None
                store.save(job)
            except IngestError as exc:
                _error_job(store, job, exc, "TRANSCRIPTION")
                raise

        request_path = Path(job.local_folder) / "localization_request.json"
        create_localization_request(
            request_path,
            video_id=job.video_id,
            caption=job.caption,
            transcript=str(transcript.get("text") or ""),
            source_language=job.language,
        )
        job.overall_status = "AWAITING_LOCALIZATION"
        job.localization_status = "PENDING"
        store.save(job)
        return _job_result(
            job,
            localization_request=str(request_path),
            next_action="按照 references/localization-policy.md 生成本土化 JSON，然后运行 apply-localization。",
        )


def apply_localization_result(settings: Settings, *, video_id: str, input_path: Path) -> dict[str, Any]:
    with StateStore(settings.state_db) as store:
        job = store.get("tiktok", video_id)
        if not job:
            raise IngestError(f"找不到 Video ID {video_id} 的本地任务。")
        output_path = Path(job.local_folder) / "localized.json"
        try:
            apply_localization(input_path, output_path, expected_video_id=video_id)
        except IngestError as exc:
            _error_job(store, job, exc, "LOCALIZATION")
            raise
        job.localization_path = str(output_path)
        job.localization_status = "SUCCESS"
        job.overall_status = "LOCALIZED"
        job.last_completed_stage = "LOCALIZATION"
        job.error_code = None
        job.error_message = None
        store.save(job)
        return _job_result(job, localization_path=str(output_path), next_action="运行 sync 同步飞书；若尚未配置，任务会保留为待同步。")


def repair_audio(settings: Settings, *, video_id: str) -> dict[str, Any]:
    with StateStore(settings.state_db) as store:
        job = store.get("tiktok", video_id)
        if not job:
            raise IngestError(f"找不到 Video ID {video_id} 的本地任务。")
        result = repair_audio_download(settings, job)
        job = result["job"]
        job.overall_status = "DOWNLOADED"
        job.download_status = "SUCCESS"
        job.transcription_status = "PENDING"
        job.localization_status = "PENDING"
        job.sync_status = "PENDING"
        job.last_completed_stage = "DOWNLOAD"
        job.error_code = None
        job.error_message = None
        store.save(job)
        return _job_result(
            job,
            backup_path=result["backup_path"],
            selected_format=result["selected_format"],
            media=result["media"],
            next_action="重新运行 ingest，仅重做转写和后续阶段。",
        )


def sync(settings: Settings, *, video_id: str) -> dict[str, Any]:
    with StateStore(settings.state_db) as store:
        job = store.get("tiktok", video_id)
        if not job:
            raise IngestError(f"找不到 Video ID {video_id} 的本地任务。")
        if not settings.feishu_configured:
            job.sync_status = "PENDING_CONFIGURATION"
            job.overall_status = "PENDING_SYNC"
            store.save(job)
            return _job_result(job, message="飞书尚未配置；本地产物和状态已保留。")
        try:
            client = FeishuClient(settings)
            cover_path: Path | None = None
            if job.local_video_path and Path(job.local_video_path).exists():
                cover_path = Path(job.local_video_path).parent / "cover.jpg"
                if not cover_path.exists():
                    info: dict[str, Any] | None = None
                    try:
                        info = probe_video(settings, job.source_url)
                    except IngestError:
                        pass
                    cover_path = create_video_cover(settings, Path(job.local_video_path), info=info)
            fields = build_fields(settings, job)
            fields[settings.feishu_field_map["processing_status"]] = "SYNCED"
            record_id = client.upsert(job, fields, cover_path=cover_path)
        except IngestError as exc:
            _error_job(store, job, exc, "SYNC")
            raise
        job.remote_record_id = record_id
        job.sync_status = "SUCCESS"
        job.overall_status = "SYNCED"
        job.last_completed_stage = "SYNC"
        job.error_code = None
        job.error_message = None
        store.save(job)
        return _job_result(job, remote_record_id=record_id, message="收录完成并已同步飞书。")

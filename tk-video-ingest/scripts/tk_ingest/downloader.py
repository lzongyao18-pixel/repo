from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import Settings
from .errors import DependencyMissingError, DownloadError
from .models import VideoJob, write_json_atomic
from .media import inspect_media, resolve_ffmpeg
from .parser import validate_tiktok_url
from .security import safe_child, sanitize_category


def _creator_name(info: dict[str, Any]) -> str:
    """Prefer a human-readable account handle over TikTok's numeric account ID."""
    return str(info.get("uploader") or info.get("creator") or info.get("uploader_id") or "")


def _hashtags(info: dict[str, Any]) -> list[str]:
    tags = info.get("tags") or []
    if tags:
        return list(dict.fromkeys(str(tag).lstrip("#") for tag in tags if str(tag).strip()))
    caption = str(info.get("description") or info.get("title") or "")
    return list(dict.fromkeys(re.findall(r"#([\w\-]+)", caption, flags=re.UNICODE)))


PREFERRED_FORMAT = "best[vcodec^=h264][acodec!=none]/best[acodec!=none]/best"
MAX_COVER_SOURCE_BYTES = 20 * 1024 * 1024


def _download_cover_source(url: str, target: Path) -> None:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=30) as response:
            declared_size = int(response.headers.get("Content-Length") or 0)
            if declared_size > MAX_COVER_SOURCE_BYTES:
                raise DownloadError("TikTok 封面超过 20 MB 限制。")
            content = response.read(MAX_COVER_SOURCE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise DownloadError("无法下载 TikTok 官方封面。", detail=str(exc)) from exc
    if not content or len(content) > MAX_COVER_SOURCE_BYTES:
        raise DownloadError("TikTok 官方封面为空或超过 20 MB 限制。")
    target.write_bytes(content)


def _render_cover(ffmpeg: str, source: Path, target: Path, *, seek_seconds: float | None = None) -> None:
    temporary = target.with_suffix(".jpg.tmp")
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if seek_seconds is not None:
        command.extend(["-ss", str(seek_seconds)])
    command.extend([
        "-i", str(source), "-frames:v", "1",
        "-vf", "scale=720:-2:force_original_aspect_ratio=decrease",
        "-q:v", "2", "-f", "image2", str(temporary),
    ])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        temporary.unlink(missing_ok=True)
        raise DownloadError("FFmpeg 生成视频封面失败。", detail=str(exc)) from exc
    if result.returncode != 0 or not temporary.exists() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise DownloadError("FFmpeg 无法生成视频封面。", detail=result.stderr[-1000:])
    temporary.replace(target)


def create_video_cover(
    settings: Settings,
    video_path: Path,
    *,
    info: dict[str, Any] | None = None,
) -> Path:
    """Create cover.jpg from TikTok's official thumbnail, falling back to the first second."""
    cover_path = video_path.parent / "cover.jpg"
    if cover_path.exists() and cover_path.stat().st_size > 0:
        return cover_path
    ffmpeg = resolve_ffmpeg(settings)
    if not ffmpeg:
        raise DependencyMissingError("生成视频封面需要 FFmpeg。")
    source_path = video_path.parent / "cover.source"
    thumbnail_url = str((info or {}).get("thumbnail") or "").strip()
    if thumbnail_url:
        try:
            _download_cover_source(thumbnail_url, source_path)
            _render_cover(ffmpeg, source_path, cover_path)
            return cover_path
        except DownloadError:
            pass
        finally:
            source_path.unlink(missing_ok=True)
    _render_cover(ffmpeg, video_path, cover_path, seek_seconds=1.0)
    return cover_path


def _find_downloaded_video(folder: Path, stem: str = "original") -> Path:
    candidates = [
        path for path in folder.glob(f"{stem}.*")
        if path.stem == stem and path.suffix.lower() not in {".json", ".part", ".ytdl", ".temp"}
    ]
    if not candidates:
        raise DownloadError("yt-dlp 未生成可识别的视频文件。")
    return max(candidates, key=lambda item: item.stat().st_size)


def _download_candidate(
    settings: Settings,
    url: str,
    folder: Path,
    *,
    stem: str,
    format_selector: str = PREFERRED_FORMAT,
) -> tuple[Path, dict[str, Any]]:
    try:
        import yt_dlp
    except ImportError as exc:
        raise DependencyMissingError("缺少 yt-dlp；请安装 assets/requirements.txt 中的依赖。") from exc
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "continuedl": False,
        "overwrites": True,
        "retries": 3,
        "fragment_retries": 3,
        "format": format_selector,
        "outtmpl": str(folder / f"{stem}.%(ext)s"),
        "writeinfojson": False,
    }
    if settings.cookie_file:
        options["cookiefile"] = str(settings.cookie_file)
    if settings.cookies_from_browser:
        options["cookiesfrombrowser"] = (settings.cookies_from_browser, None, None, None)
    ffmpeg_location = resolve_ffmpeg(settings)
    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
    return _find_downloaded_video(folder, stem), info


def _next_backup_path(video_path: Path) -> Path:
    candidate = video_path.with_name(f"original.no-audio{video_path.suffix}")
    counter = 2
    while candidate.exists():
        candidate = video_path.with_name(f"original.no-audio-{counter}{video_path.suffix}")
        counter += 1
    return candidate


def probe_video(settings: Settings, url: str) -> dict[str, Any]:
    try:
        import yt_dlp
    except ImportError as exc:
        raise DependencyMissingError("缺少 yt-dlp；请安装 assets/requirements.txt 中的依赖。") from exc

    safe_url = validate_tiktok_url(url)
    probe_options: dict[str, Any] = {"quiet": True, "no_warnings": True, "skip_download": True}
    if settings.cookie_file:
        probe_options["cookiefile"] = str(settings.cookie_file)
    if settings.cookies_from_browser:
        probe_options["cookiesfrombrowser"] = (settings.cookies_from_browser, None, None, None)
    ffmpeg_location = resolve_ffmpeg(settings)
    if ffmpeg_location:
        probe_options["ffmpeg_location"] = ffmpeg_location

    try:
        with yt_dlp.YoutubeDL(probe_options) as ydl:
            info = ydl.extract_info(safe_url, download=False)
        if info and "entries" in info:
            entries = [entry for entry in info.get("entries") or [] if entry]
            if len(entries) != 1:
                raise DownloadError("该链接没有唯一对应到一个视频。")
            info = entries[0]
        video_id = str((info or {}).get("id") or "").strip()
        if not video_id:
            raise DownloadError("无法从 TikTok 元数据中取得 Video ID。")
        return info
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError("无法读取 TikTok 视频元数据。", detail=str(exc)) from exc


def download_video(
    settings: Settings,
    url: str,
    category: str,
    *,
    probed_info: dict[str, Any] | None = None,
) -> tuple[VideoJob, dict[str, Any]]:
    try:
        import yt_dlp
    except ImportError as exc:
        raise DependencyMissingError("缺少 yt-dlp；请安装 assets/requirements.txt 中的依赖。") from exc

    safe_url = validate_tiktok_url(url)
    safe_category = sanitize_category(category, default=settings.default_category)
    info = probed_info or probe_video(settings, safe_url)
    video_id = str(info.get("id") or "").strip()
    try:
        video_folder = safe_child(settings.library_root, safe_category, video_id)
        video_folder.mkdir(parents=True, exist_ok=True)
        if any(path.stem == "original" for path in video_folder.glob("original.*")):
            raise DownloadError("目标视频文件已存在；请使用恢复或音轨修复流程。")
        candidate_path, downloaded_info = _download_candidate(settings, safe_url, video_folder, stem="incoming")
        info = downloaded_info or info
        media = inspect_media(candidate_path)
        if not media["has_video"]:
            raise DownloadError("下载文件不包含视频流。")
        video_path = candidate_path.with_name(f"original{candidate_path.suffix}")
        candidate_path.replace(video_path)
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError("TikTok 下载失败。", detail=str(exc)) from exc

    canonical_url = str(info.get("webpage_url") or info.get("original_url") or safe_url)
    metadata_path = video_folder / "metadata.json"
    cover_path: Path | None = None
    cover_error: str | None = None
    try:
        cover_path = create_video_cover(settings, video_path, info=info)
    except DownloadError as exc:
        cover_error = exc.message
    normalized = {
        "platform": "tiktok",
        "video_id": video_id,
        "source_url": safe_url,
        "canonical_url": canonical_url,
        "creator": _creator_name(info),
        "creator_display_name": info.get("uploader") or info.get("creator"),
        "publish_time": info.get("timestamp") or info.get("upload_date"),
        "caption": info.get("description") or info.get("title") or "",
        "hashtags": _hashtags(info),
        "duration": info.get("duration"),
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "selected_format": info.get("format_id"),
        "media": media,
        "video_path": str(video_path),
        "cover_path": str(cover_path) if cover_path else None,
        "cover_error": cover_error,
    }
    write_json_atomic(metadata_path, normalized)
    job = VideoJob(
        platform="tiktok",
        video_id=video_id,
        source_url=safe_url,
        canonical_url=canonical_url,
        category=safe_category,
        creator=str(normalized["creator"] or ""),
        publish_time=str(normalized["publish_time"] or "") or None,
        caption=str(normalized["caption"]),
        hashtags=list(normalized["hashtags"]),
        duration=float(normalized["duration"]) if normalized["duration"] is not None else None,
        local_folder=str(video_folder),
        local_video_path=str(video_path),
        metadata_path=str(metadata_path),
        overall_status="DOWNLOADED",
        download_status="SUCCESS",
        last_completed_stage="DOWNLOAD",
    )
    return job, normalized


def repair_audio_download(settings: Settings, job: VideoJob) -> dict[str, Any]:
    if not job.local_video_path or not Path(job.local_video_path).exists():
        raise DownloadError("找不到需要修复的本地视频文件。")
    video_path = Path(job.local_video_path)
    folder = video_path.parent
    try:
        candidate_path, info = _download_candidate(settings, job.source_url, folder, stem="replacement")
        media = inspect_media(candidate_path)
        if not media["has_video"] or not media["has_audio"]:
            candidate_path.unlink(missing_ok=True)
            raise DownloadError("替换格式仍未包含完整的音频和视频流。")
        backup_path = _next_backup_path(video_path)
        video_path.replace(backup_path)
        repaired_path = candidate_path.with_name(f"original{candidate_path.suffix}")
        try:
            candidate_path.replace(repaired_path)
        except Exception:
            backup_path.replace(video_path)
            raise
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError("重新下载有声格式失败。", detail=str(exc)) from exc

    metadata_path = Path(job.metadata_path) if job.metadata_path else folder / "metadata.json"
    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            import json

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
    metadata.update(
        {
            "video_path": str(repaired_path),
            "selected_format": info.get("format_id"),
            "media": media,
            "repaired_from": str(backup_path),
        }
    )
    write_json_atomic(metadata_path, metadata)
    job.local_video_path = str(repaired_path)
    job.metadata_path = str(metadata_path)
    return {
        "job": job,
        "video_path": str(repaired_path),
        "backup_path": str(backup_path),
        "selected_format": info.get("format_id"),
        "media": media,
    }

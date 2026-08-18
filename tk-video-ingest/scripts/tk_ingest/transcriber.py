from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Settings
from .errors import DependencyMissingError, TranscriptionError
from .models import write_json_atomic


def _has_audio_stream(video_path: Path) -> bool | None:
    try:
        import av

        with av.open(str(video_path)) as container:
            return any(stream.type == "audio" for stream in container.streams)
    except (ImportError, OSError, RuntimeError, ValueError):
        return None


def transcribe_video(settings: Settings, video_path: Path, output_path: Path) -> dict[str, Any]:
    has_audio = _has_audio_stream(video_path)
    if has_audio is False:
        payload = {
            "text": "",
            "language": None,
            "language_probability": None,
            "segments": [],
            "model": settings.whisper_model,
            "device": settings.whisper_device,
            "compute_type": settings.whisper_compute_type,
            "note": "视频无音轨",
        }
        write_json_atomic(output_path, payload)
        return payload
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise DependencyMissingError("缺少 faster-whisper；请安装 assets/requirements.txt 中的依赖。") from exc
    try:
        model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            download_root=str(settings.whisper_cache_dir),
        )
        segments_iter, info = model.transcribe(
            str(video_path),
            language=settings.whisper_language,
            vad_filter=True,
            beam_size=5,
        )
        segments = [
            {"start": round(segment.start, 3), "end": round(segment.end, 3), "text": segment.text.strip()}
            for segment in segments_iter
            if segment.text.strip()
        ]
    except Exception as exc:
        raise TranscriptionError("本地语音转写失败。", detail=str(exc)) from exc
    payload = {
        "text": " ".join(segment["text"] for segment in segments).strip(),
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "segments": segments,
        "model": settings.whisper_model,
        "device": settings.whisper_device,
        "compute_type": settings.whisper_compute_type,
    }
    if not payload["text"]:
        payload["note"] = "无可识别语音"
    write_json_atomic(output_path, payload)
    return payload

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import Settings


def resolve_ffmpeg(settings: Settings) -> str | None:
    if settings.ffmpeg_location:
        configured = Path(settings.ffmpeg_location).expanduser()
        if configured.exists():
            return str(configured.resolve())
        found = shutil.which(settings.ffmpeg_location)
        if found:
            return found
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        bundled = Path(imageio_ffmpeg.get_ffmpeg_exe())
        return str(bundled.resolve()) if bundled.exists() else None
    except (ImportError, RuntimeError, OSError):
        return None


def inspect_media(path: Path) -> dict[str, Any]:
    import av

    with av.open(str(path)) as container:
        streams = [
            {
                "index": stream.index,
                "type": stream.type,
                "codec": getattr(stream.codec_context, "name", None),
            }
            for stream in container.streams
        ]
    return {
        "has_video": any(stream["type"] == "video" for stream in streams),
        "has_audio": any(stream["type"] == "audio" for stream in streams),
        "streams": streams,
    }

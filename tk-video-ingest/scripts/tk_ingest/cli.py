from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from .config import Settings
from .errors import IngestError
from .parser import parse_instruction
from .media import resolve_ffmpeg
from .security import redact
from .state import StateStore
from .workflow import apply_localization_result, ingest, repair_audio, sync


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tk-video-ingest", description="Collect one TikTok video into a local material library.")
    parser.add_argument("--env-file", type=Path, help="Path to a private .env file.")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_cmd = sub.add_parser("ingest", help="Download, transcribe, and prepare localization for one video.")
    ingest_cmd.add_argument("--url", required=True)
    ingest_cmd.add_argument("--folder")
    ingest_cmd.add_argument("--skip-transcription", action="store_true")

    parse_cmd = sub.add_parser("parse", help="Parse a natural-language collection instruction.")
    parse_cmd.add_argument("instruction")

    localize_cmd = sub.add_parser("apply-localization", help="Validate and store a Codex-produced localization JSON file.")
    localize_cmd.add_argument("--video-id", required=True)
    localize_cmd.add_argument("--json-file", required=True, type=Path)

    sync_cmd = sub.add_parser("sync", help="Create or update the Feishu record for a local job.")
    sync_cmd.add_argument("--video-id", required=True)

    repair_cmd = sub.add_parser("repair-audio", help="Redownload an H.264 format, verify audio, and preserve the old file as a backup.")
    repair_cmd.add_argument("--video-id", required=True)

    status_cmd = sub.add_parser("status", help="Show one job or all pending jobs.")
    status_cmd.add_argument("--video-id")

    sub.add_parser("check", help="Check local dependencies and configuration without network mutations.")
    return parser


def _check(settings: Settings) -> dict[str, Any]:
    return {
        "library_root": str(settings.library_root),
        "library_root_exists": settings.library_root.exists(),
        "state_db": str(settings.state_db),
        "yt_dlp_installed": importlib.util.find_spec("yt_dlp") is not None,
        "faster_whisper_installed": importlib.util.find_spec("faster_whisper") is not None,
        "ffmpeg": resolve_ffmpeg(settings),
        "feishu_configured": settings.feishu_configured,
        "ready_for_local_processing": importlib.util.find_spec("yt_dlp") is not None and importlib.util.find_spec("faster_whisper") is not None,
    }


def _status(settings: Settings, video_id: str | None) -> dict[str, Any]:
    with StateStore(settings.state_db) as store:
        if video_id:
            job = store.get("tiktok", video_id)
            return {"job": job.to_dict() if job else None}
        return {"pending": [job.to_dict() for job in store.list_pending()]}


def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = Settings.load(args.env_file)
        if args.command == "ingest":
            result = ingest(settings, url=args.url, category=args.folder, skip_transcription=args.skip_transcription)
        elif args.command == "parse":
            request = parse_instruction(args.instruction, default_category=settings.default_category)
            result = {"url": request.url, "category": request.category}
        elif args.command == "apply-localization":
            result = apply_localization_result(settings, video_id=args.video_id, input_path=args.json_file)
        elif args.command == "sync":
            result = sync(settings, video_id=args.video_id)
        elif args.command == "repair-audio":
            result = repair_audio(settings, video_id=args.video_id)
        elif args.command == "status":
            result = _status(settings, args.video_id)
        else:
            result = _check(settings)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except IngestError as exc:
        error = {"status": "FAILED", "error_code": exc.code, "message": redact(exc.message)}
        if exc.detail:
            error["detail"] = redact(exc.detail)[:1000]
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

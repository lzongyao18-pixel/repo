# Configuration

Use a private `.env` outside the Skill folder for secrets. Start from `assets/env.example`; never commit the populated file.

## Required for local processing

- Python 3.10 or newer
- `yt-dlp`
- `faster-whisper`
- FFmpeg available on `PATH` for yt-dlp format merging
- Adequate storage under `TK_LIBRARY_ROOT`

Install the pinned-compatible ranges from `assets/requirements.txt` in the Python environment used to run the Skill.

On this Windows project, create `.venv` at the workspace root. Use `scripts/run.ps1` so the Skill selects that interpreter automatically. If the runtime lives elsewhere, set `TK_INGEST_PYTHON` to its full `python.exe` path.

## Local settings

- `TK_LIBRARY_ROOT`: default `D:\TK素材库`
- `TK_DEFAULT_CATEGORY`: default `待分类`
- `TK_STATE_DB`: default `<root>\.system\tk_ingest.db`
- `TK_MACHINE_ID`: stable identifier for this workstation
- `YTDLP_COOKIE_FILE`: optional Netscape cookie file
- `YTDLP_COOKIES_FROM_BROWSER`: optional browser name accepted by yt-dlp
- `FFMPEG_LOCATION`: optional FFmpeg executable or directory; when empty, use PATH or bundled `imageio-ffmpeg`

Prefer public videos without cookies. If authentication is necessary, use only the user's own authorized session and keep cookie material outside logs and repositories.

## Whisper settings

- `WHISPER_MODEL`: start with `small`
- `WHISPER_DEVICE`: `auto`, `cpu`, or `cuda`
- `WHISPER_COMPUTE_TYPE`: start with `auto`; benchmark the target machine
- `WHISPER_LANGUAGE`: empty for automatic detection
- `WHISPER_CACHE_DIR`: default `<root>\.models`

Run `check` before the first real ingest. Benchmark at least one short and one long sample on the target machine before changing the defaults.

## Feishu settings

Leave these empty until the self-built app and Bitable are created:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_BITABLE_APP_TOKEN`
- `FEISHU_TABLE_ID`
- `FEISHU_FIELD_MAP_JSON`

The runtime treats incomplete Feishu configuration as recoverable and keeps jobs in `PENDING_SYNC`.

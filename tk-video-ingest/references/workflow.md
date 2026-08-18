# Workflow and recovery

## Contents

- Stage model
- Ingest sequence
- Recovery decisions
- Output files

## Stage model

Track download, transcription, localization, and synchronization independently. Store the overall status only as a summary.

Normal sequence:

```text
RECEIVED -> DOWNLOADED -> TRANSCRIBED -> AWAITING_LOCALIZATION
         -> LOCALIZED -> PENDING_SYNC -> SYNCED
```

Failures use `FAILED_<STAGE>` while retaining `last_completed_stage` and all finished artifacts.

## Ingest sequence

1. Validate the TikTok host and category.
2. Extract a direct Video ID when possible.
3. Check SQLite and existing files before any download.
4. Probe yt-dlp metadata; resolve short links through yt-dlp.
5. Check SQLite again using the resolved Video ID.
6. Prefer the highest muxed H.264 format that declares audio and download it to a temporary filename.
7. Inspect the actual media streams, then atomically move the verified candidate to `original.<ext>`.
8. Save TikTok's official thumbnail as `cover.jpg`; if unavailable, extract the frame at one second. Write `metadata.json`.
9. Transcribe to `transcript.json`.
10. Write `localization_request.json` and pause for Codex.
11. Validate Codex output into `localized.json`.
12. Search Feishu by exact Video ID, upload a missing cover as a Bitable attachment, and create or update one record.

## Recovery decisions

- `SYNCED` with an existing video: return duplicate without downloading.
- Video exists and transcription failed: rerun transcription and later stages only.
- Localization failed: preserve caption and transcript; reapply a corrected JSON file.
- Feishu is unconfigured or unavailable: retain `PENDING_SYNC`; run `sync` later.
- More than one Feishu match: stop with a duplicate-remote-record error; never choose a row silently.
- Missing local file despite a successful download status: treat the download as incomplete and download again.
- Unexpected missing audio: run `repair-audio`; download an H.264 candidate, require both audio and video streams, retain the old file as `original.no-audio.<ext>`, and reset transcription/localization/sync for recovery.

## Output files

```text
<TK_LIBRARY_ROOT>/
  .system/tk_ingest.db
  .models/
  <category>/<video_id>/
    original.<ext>
    cover.jpg
    metadata.json
    transcript.json
    localization_request.json
    localized.json
```

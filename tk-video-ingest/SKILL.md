---
name: tk-video-ingest
description: Collect one public TikTok video into a Windows material library with local deduplication, yt-dlp download, faster-whisper transcription, natural Chinese localization, resumable SQLite state, and optional Feishu Bitable synchronization. Use when the user says “收录” or “收录到：分类” with one TikTok video URL, asks to resume or inspect a TikTok collection job, or wants to retry localization or Feishu synchronization for previously downloaded material. Do not use for publishing, automated editing, bulk imports, or videos the user is not authorized to save.
---

# TikTok Video Ingest

Use Codex for instruction parsing, localization judgment, and user-facing summaries. Use `scripts/main.py` for deterministic downloading, transcription, state transitions, validation, and Feishu API operations.

## Route the request

- For `收录 <TikTok URL>`: use the configured default category.
- For `收录到：<分类> <TikTok URL>`: pass the relative category with `--folder`.
- For retry or status requests: obtain the Video ID and run `status`, `ingest`, or `sync` as appropriate.
- For a downloaded video that unexpectedly lacks audio: run `repair-audio`, verify the reported audio stream, then run `ingest` again to redo transcription and localization.
- Reject multiple URLs in V1. Never process a link the user is not authorized to save.

Read [references/workflow.md](references/workflow.md) before the first ingest or recovery operation. Read [references/configuration.md](references/configuration.md) when setup or dependency checks fail. Read [references/feishu-schema.md](references/feishu-schema.md) before configuring or changing the Feishu table.

## Run the workflow

1. Run a read-only readiness check:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1 --env-file <private-env-path> check
   ```

2. Start or resume exactly one video:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1 --env-file <private-env-path> ingest --url "<url>" --folder "<category>"
   ```

3. If the command returns `AWAITING_LOCALIZATION`, read the returned `localization_request` file and [references/localization-policy.md](references/localization-policy.md). Produce a UTF-8 JSON file containing exactly one matching `video_id`, `caption_zh_localized`, and `transcript_zh_localized`. Do not invent speech when the transcript is empty.

4. Validate and apply the localization result:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1 --env-file <private-env-path> apply-localization --video-id <id> --json-file <result.json>
   ```

5. Synchronize after localization:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1 --env-file <private-env-path> sync --video-id <id>
   ```

For unexpected missing audio, preserve the old file and repair deterministically:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1 --env-file <private-env-path> repair-audio --video-id <id>
```

If Feishu is not configured, accept `PENDING_SYNC` as a recoverable partial success. Do not rerun the download merely because remote sync is unavailable.

## Enforce safety and recovery

- Keep every category under `TK_LIBRARY_ROOT`; reject absolute paths, `..`, UNC paths, and Windows reserved names.
- Treat `platform + video_id` as the unique key. Check local SQLite state and local files before remote state.
- Preserve the original video, `cover.jpg`, metadata, transcript, localization, and database record after downstream failures.
- Prefer a muxed H.264 format with audio. Inspect the actual downloaded streams instead of trusting TikTok format metadata alone.
- Prefer TikTok's official thumbnail for `cover.jpg`; fall back to the frame at one second. Upload it once to the Feishu `Video Cover` attachment field and preserve an existing attachment during retries.
- Retry only recoverable network or service failures with a finite limit. Do not blindly retry invalid input, missing permission, or missing configuration.
- Never print or copy App Secrets, tenant tokens, browser cookies, or full authorization headers into chat or ordinary logs.
- Do not overwrite source media or delete partial artifacts without explicit user approval.

## Report the result

Return one of: `SYNCED`, `DUPLICATE`, `AWAITING_LOCALIZATION`, `PENDING_SYNC`, `FAILED_DOWNLOAD`, `FAILED_TRANSCRIPTION`, `FAILED_LOCALIZATION`, or `FAILED_SYNC`.

Include the Video ID, local video path, completed stages, Feishu state, and one concrete next action when the result is not fully synchronized. Do not expose secrets or raw stack traces.

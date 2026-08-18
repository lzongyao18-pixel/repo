# Chinese localization policy

Produce natural Chinese localizations. Preserve the source Caption and Transcript unchanged in their original files.

## Required JSON shape

```json
{
  "video_id": "1234567890",
  "caption_zh_localized": "",
  "transcript_zh_localized": "",
  "provider": "codex",
  "model": "codex-current",
  "prompt_version": "v1"
}
```

## Rules

- Make `*_localized` natural for a Chinese viewer while preserving quantities, product claims, negation, uncertainty, names, calls to action, and all other factual meaning.
- Do not add performance claims, prices, certifications, scarcity, guarantees, or product features absent from the source.
- Keep hashtags only when meaningful; localize their wording without inventing trends.
- Use an empty string for an empty source. Never infer speech from visuals or music.
- Preserve ambiguous names or terms and choose a conservative translation.
- Do not censor ordinary colloquial language unless the user requests a brand-specific tone.

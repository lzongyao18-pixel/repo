# Feishu Bitable schema

Create one Bitable and one table before enabling synchronization. Grant the self-built app only the record read, create, update, and necessary metadata permissions for that Base.

## Required fields

| Field name | Suggested type | Purpose |
|---|---|---|
| Video ID | Text | Unique business key; never use number type |
| Video Cover | Attachment | Persistent preview uploaded as `cover.jpg` |
| Source URL | URL | Canonical TikTok link |
| Creator | Text | Creator identifier or display name |
| Publish Time | Text | China-time date formatted as `YYYY-MM-DD` |
| Caption | Long text | Original caption |
| Hashtags | Text | Normalized hashtags for V1 |
| Transcript | Long text | Original-language transcript |
| Caption ZH Localized | Long text | Natural Chinese localization |
| Transcript ZH Localized | Long text | Natural Chinese localization |
| Relative Path | Text | Path relative to the material root |
| Machine ID | Text | Workstation identity |
| Duration | Number | Seconds |
| Processing Status | Single select or Text | Current summary state |
| Error Message | Long text | Sanitized user-readable error |

## Setup checks

1. Make `Video ID` plain text so long numeric IDs are not rounded.
2. Make `Video Cover` an attachment field; upload `cover.jpg` as `bitable_image` before writing its `file_token`.
3. Ensure the app has access to the Base, not only API scopes.
4. Enter the Base app token and table ID in the private `.env`.
5. Override display names through `FEISHU_FIELD_MAP_JSON` if the table differs.
6. Run `check`, then sync one test record.
7. Submit the same Video ID twice and confirm that only one row and one cover attachment remain.

The API cannot guarantee uniqueness by field value. The runtime serializes local work with SQLite and stops if Feishu already contains multiple matching records.

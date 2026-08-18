from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from tk_ingest.config import Settings
from tk_ingest.feishu import FeishuClient, _encode_multipart, build_fields, format_publish_date
from tk_ingest.models import VideoJob


class PublishDateFormattingTests(unittest.TestCase):
    def test_formats_unix_seconds_in_china_time(self) -> None:
        self.assertEqual(format_publish_date("1765133651"), "2025-12-08")

    def test_formats_yt_dlp_compact_date(self) -> None:
        self.assertEqual(format_publish_date("20260814"), "2026-08-14")

    def test_formats_iso_timestamp(self) -> None:
        self.assertEqual(format_publish_date("2026-08-13T18:00:00Z"), "2026-08-14")

    def test_preserves_already_formatted_date(self) -> None:
        self.assertEqual(format_publish_date("2026-08-14"), "2026-08-14")

    def test_empty_value_stays_empty(self) -> None:
        self.assertEqual(format_publish_date(None), "")

    def test_removed_columns_are_not_sent_to_feishu(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(library_root=Path(temp))
            job = VideoJob(
                platform="tiktok",
                video_id="12345678",
                source_url="https://www.tiktok.com/@x/video/12345678",
            )
            fields = build_fields(settings, job)
        removed = {
            "Caption ZH Literal",
            "Transcript ZH Literal",
            "Absolute Path",
            "Language",
            "Download Time",
        }
        self.assertTrue(removed.isdisjoint(fields))

    def test_cover_upload_multipart_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            cover = Path(temp) / "cover.jpg"
            cover.write_bytes(b"jpeg-data")
            body, content_type = _encode_multipart(
                {"parent_type": "bitable_image", "size": "9"},
                file_field="file",
                file_path=cover,
                boundary="test-boundary",
            )
        self.assertEqual(content_type, "multipart/form-data; boundary=test-boundary")
        self.assertIn(b'name="parent_type"', body)
        self.assertIn(b"bitable_image", body)
        self.assertIn(b'filename="cover.jpg"', body)
        self.assertIn(b"jpeg-data", body)

    def test_existing_remote_cover_is_not_uploaded_again(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cover = root / "cover.jpg"
            cover.write_bytes(b"jpeg-data")
            settings = Settings(
                library_root=root,
                feishu_app_id="app-id",
                feishu_app_secret="secret",
                feishu_app_token="app-token",
                feishu_table_id="table-id",
            )
            job = VideoJob(
                platform="tiktok",
                video_id="12345678",
                source_url="https://www.tiktok.com/@x/video/12345678",
                remote_record_id="record-id",
            )
            existing = [{"record_id": "record-id", "fields": {"Video Cover": [{"file_token": "existing"}]}}]
            with patch.object(FeishuClient, "search_video_id", return_value=existing), patch.object(
                FeishuClient, "upload_cover"
            ) as upload, patch("tk_ingest.feishu._request_json", return_value={"data": {"record": {"record_id": "record-id"}}}):
                client = FeishuClient(settings)
                client._token = "token"
                record_id = client.upsert(job, {"Video ID": job.video_id}, cover_path=cover)
            self.assertEqual(record_id, "record-id")
            upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()

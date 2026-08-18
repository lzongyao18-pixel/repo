from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from tk_ingest.config import Settings
from tk_ingest.downloader import _creator_name, create_video_cover
from tk_ingest.errors import DownloadError


class CreatorNameTests(unittest.TestCase):
    def test_prefers_readable_uploader_over_numeric_id(self) -> None:
        info = {"uploader": "2poor4prada", "uploader_id": "7161251965325362222"}
        self.assertEqual(_creator_name(info), "2poor4prada")

    def test_falls_back_to_numeric_id(self) -> None:
        self.assertEqual(_creator_name({"uploader_id": "7161251965325362222"}), "7161251965325362222")

    def test_cover_falls_back_to_video_frame(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / "original.mp4"
            video.write_bytes(b"video")

            def fake_render(_ffmpeg, source, target, *, seek_seconds=None):
                self.assertEqual(source, video)
                self.assertEqual(seek_seconds, 1.0)
                target.write_bytes(b"cover")

            with patch("tk_ingest.downloader.resolve_ffmpeg", return_value="ffmpeg"), patch(
                "tk_ingest.downloader._download_cover_source",
                side_effect=DownloadError("thumbnail unavailable"),
            ), patch("tk_ingest.downloader._render_cover", side_effect=fake_render):
                cover = create_video_cover(
                    Settings(library_root=root),
                    video,
                    info={"thumbnail": "https://example.com/cover.webp"},
                )
            self.assertEqual(cover.read_bytes(), b"cover")


if __name__ == "__main__":
    unittest.main()

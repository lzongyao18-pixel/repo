import tempfile
import unittest
from pathlib import Path

from tk_ingest.errors import InvalidInputError
from tk_ingest.parser import extract_video_id, parse_instruction
from tk_ingest.security import redact, safe_child, sanitize_category
from tk_ingest.downloader import PREFERRED_FORMAT, _find_downloaded_video


class ParserSecurityTests(unittest.TestCase):
    def test_default_instruction(self):
        request = parse_instruction("收录 https://www.tiktok.com/@shop/video/1234567890123456789")
        self.assertEqual(request.category, "待分类")
        self.assertEqual(extract_video_id(request.url), "1234567890123456789")

    def test_named_category(self):
        request = parse_instruction("收录到：保温杯竞品 https://vm.tiktok.com/abc/")
        self.assertEqual(request.category, "保温杯竞品")

    def test_multiple_urls_rejected(self):
        with self.assertRaises(InvalidInputError):
            parse_instruction("收录 https://vm.tiktok.com/a https://vm.tiktok.com/b")

    def test_unsafe_categories_rejected(self):
        for value in (r"D:\escape", r"..\escape", r"\\server\share", "CON"):
            with self.subTest(value=value), self.assertRaises(InvalidInputError):
                sanitize_category(value)

    def test_safe_child_cannot_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(safe_child(root, "分类", "123").parent.name, "分类")
            with self.assertRaises(InvalidInputError):
                safe_child(root, "..", "escape")

    def test_redaction(self):
        redacted = redact("app_secret=abc access_token: xyz Cookie=secret")
        self.assertNotIn("abc", redacted)
        self.assertNotIn("xyz", redacted)
        self.assertNotIn("Cookie=secret", redacted)

    def test_download_selection_prefers_h264_audio(self):
        self.assertIn("vcodec^=h264", PREFERRED_FORMAT)
        self.assertIn("acodec!=none", PREFERRED_FORMAT)

    def test_download_finder_ignores_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = root / "original.mp4"
            backup = root / "original.no-audio.mp4"
            current.write_bytes(b"new")
            backup.write_bytes(b"larger-old-backup")
            self.assertEqual(_find_downloaded_video(root), current)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from tk_ingest.errors import LocalizationError
from tk_ingest.config import Settings
from tk_ingest.localizer import apply_localization
from tk_ingest.models import VideoJob
from tk_ingest.state import StateStore
from tk_ingest.workflow import sync
from tk_ingest.workflow import ingest
from tk_ingest.workflow import repair_audio
from tk_ingest.transcriber import _has_audio_stream


class StateLocalizationTests(unittest.TestCase):
    def test_no_audio_stream_is_detected(self):
        fake_container = MagicMock()
        fake_container.__enter__.return_value.streams = [SimpleNamespace(type="video")]
        fake_av = SimpleNamespace(open=lambda _: fake_container)
        with patch.dict("sys.modules", {"av": fake_av}):
            self.assertFalse(_has_audio_stream(Path("video.mp4")))

    def test_state_upsert_is_unique(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "state.db"
            with StateStore(db) as store:
                job = VideoJob(platform="tiktok", video_id="12345678", source_url="https://www.tiktok.com/@x/video/12345678")
                store.save(job)
                job.overall_status = "DOWNLOADED"
                job.download_status = "SUCCESS"
                store.save(job)
                saved = store.get("tiktok", "12345678")
                self.assertEqual(saved.overall_status, "DOWNLOADED")
                count = store.connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
                self.assertEqual(count, 1)

    def test_localization_validation_and_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input.json"
            output = root / "localized.json"
            source.write_text(json.dumps({
                "video_id": "12345678",
                "caption_zh_localized": "自然",
                "transcript_zh_localized": "口语",
            }, ensure_ascii=False), encoding="utf-8")
            result = apply_localization(source, output, expected_video_id="12345678")
            self.assertEqual(result["provider"], "codex")
            self.assertTrue(output.exists())

    def test_localization_video_id_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "input.json"
            source.write_text('{"video_id":"wrong"}', encoding="utf-8")
            with self.assertRaises(LocalizationError):
                apply_localization(source, Path(temp) / "out.json", expected_video_id="expected")

    def test_sync_without_feishu_remains_pending(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings = Settings(library_root=root, state_db=root / "state.db")
            with StateStore(settings.state_db) as store:
                store.save(VideoJob(
                    platform="tiktok",
                    video_id="12345678",
                    source_url="https://www.tiktok.com/@x/video/12345678",
                    overall_status="LOCALIZED",
                    localization_status="SUCCESS",
                ))
            result = sync(settings, video_id="12345678")
            self.assertEqual(result["status"], "PENDING_SYNC")
            self.assertEqual(result["sync_status"], "PENDING_CONFIGURATION")

    def test_duplicate_does_not_destroy_synced_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / "分类" / "12345678" / "original.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")
            settings = Settings(library_root=root, state_db=root / "state.db")
            with StateStore(settings.state_db) as store:
                store.save(VideoJob(
                    platform="tiktok",
                    video_id="12345678",
                    source_url="https://www.tiktok.com/@x/video/12345678",
                    local_video_path=str(video),
                    download_status="SUCCESS",
                    localization_status="SUCCESS",
                    sync_status="SUCCESS",
                    overall_status="SYNCED",
                ))
            result = ingest(settings, url="https://www.tiktok.com/@x/video/12345678")
            self.assertEqual(result["status"], "DUPLICATE")
            with StateStore(settings.state_db) as store:
                self.assertEqual(store.get("tiktok", "12345678").overall_status, "SYNCED")

    def test_localized_job_is_not_relocalized(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "分类" / "12345678"
            folder.mkdir(parents=True)
            video = folder / "original.mp4"
            localized = folder / "localized.json"
            video.write_bytes(b"video")
            localized.write_text("{}", encoding="utf-8")
            settings = Settings(library_root=root, state_db=root / "state.db")
            with StateStore(settings.state_db) as store:
                store.save(VideoJob(
                    platform="tiktok",
                    video_id="12345678",
                    source_url="https://www.tiktok.com/@x/video/12345678",
                    local_video_path=str(video),
                    localization_path=str(localized),
                    download_status="SUCCESS",
                    transcription_status="SUCCESS",
                    localization_status="SUCCESS",
                    sync_status="FAILED",
                    overall_status="FAILED_SYNC",
                ))
            result = ingest(settings, url="https://www.tiktok.com/@x/video/12345678")
            self.assertEqual(result["status"], "PENDING_SYNC")

    def test_audio_repair_resets_downstream_stages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings = Settings(library_root=root, state_db=root / "state.db")
            job = VideoJob(
                platform="tiktok",
                video_id="12345678",
                source_url="https://www.tiktok.com/@x/video/12345678",
                download_status="SUCCESS",
                transcription_status="NO_SPEECH",
                localization_status="SUCCESS",
                sync_status="PENDING_CONFIGURATION",
                overall_status="PENDING_SYNC",
            )
            with StateStore(settings.state_db) as store:
                store.save(job)
            repaired = {
                "job": job,
                "backup_path": str(root / "original.no-audio.mp4"),
                "selected_format": "h264-test",
                "media": {"has_video": True, "has_audio": True, "streams": []},
            }
            with patch("tk_ingest.workflow.repair_audio_download", return_value=repaired):
                result = repair_audio(settings, video_id="12345678")
            self.assertEqual(result["status"], "DOWNLOADED")
            self.assertEqual(result["transcription_status"], "PENDING")
            self.assertEqual(result["localization_status"], "PENDING")
            self.assertEqual(result["sync_status"], "PENDING")


if __name__ == "__main__":
    unittest.main()

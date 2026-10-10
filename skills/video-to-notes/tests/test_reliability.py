import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import insert_images_feishu as publish
import extract_keyframes as frames
import resilient_ytdlp_download as download

class ReliabilityTests(unittest.TestCase):
    def test_vtt_html_entities_decoded(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d)/"in.vtt", Path(d)/"out.txt"
            src.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n&gt;&gt; A &amp; B\n", encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPTS/"clean_vtt.py"), str(src), str(dst)], check=True, capture_output=True)
            self.assertEqual(dst.read_text(encoding="utf-8"), "[00:00:01] >> A & B")

    def test_numeric_subtitle_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d)/"in.srt", Path(d)/"out.txt"
            src.write_text("1\n00:00:01,000 --> 00:00:02,000\n150000\n\n2\n00:00:03,000 --> 00:00:04,000\nper second\n", encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPTS/"srt_to_txt.py"), str(src), str(dst)], check=True, capture_output=True)
            self.assertEqual(dst.read_text(encoding="utf-8"), "[00:00:01] 150000\n[00:00:03] per second")

    def test_publish_preflight(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p/"image.jpg").write_bytes(b"image")
            note = p/"note.md"
            note.write_text("![demo](image.jpg)\n*Demo 来源 00:00:01*\n", encoding="utf-8")
            self.assertEqual(len(publish.collect_items(note)), 1)
            note.write_text(note.read_text(encoding="utf-8") * 2, encoding="utf-8")
            with self.assertRaises(ValueError):
                publish.collect_items(note)

    def test_failed_scene_detection_preserves_previous_frames(self):
        with tempfile.TemporaryDirectory() as d:
            old = Path(d)/"renamed"/"slide_00-00-01.jpg"
            old.parent.mkdir()
            old.write_bytes(b"previous")
            with patch.object(sys, "argv", ["extract", "bad.mp4", d]), patch.object(frames.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "invalid video")):
                with self.assertRaises(RuntimeError):
                    frames.main()
            self.assertEqual(old.read_bytes(), b"previous")

    def test_failed_large_download_does_not_replace_output(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/"video.mp4"
            out.write_bytes(b"original")
            def fail_curl(*a, **kw):
                out.with_name(out.name + ".part").write_bytes(b"x" * 2048)
                return subprocess.CompletedProcess([], 28)
            with patch.object(sys, "argv", ["download", "url", str(out), "--attempts", "1", "--min-size", "0"]), patch.object(download, "resolve_url", return_value="https://example.com/video"), patch.object(download.subprocess, "run", side_effect=fail_curl):
                with self.assertRaises(SystemExit):
                    download.main()
            self.assertEqual(out.read_bytes(), b"original")

    def test_publisher_retry_skips_confirmed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p/"image.jpg").write_bytes(b"image")
            note = p/"note.md"
            note.write_text("![demo](image.jpg)\n*Demo 来源 00:00:01*\n", encoding="utf-8")
            with patch.object(sys, "argv", ["publish", "doc", str(note)]), patch.object(publish.shutil, "which", return_value="lark-cli"), patch.object(publish.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "true", "")) as run:
                publish.main()
                publish.main()
                self.assertEqual(run.call_count, 1)
                argv = run.call_args.args[0]
                self.assertEqual(argv[argv.index("--file") + 1], "image.jpg")
                self.assertEqual(run.call_args.kwargs["cwd"], p)

    def test_publisher_uncertain_request_blocks_retry(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p/"image.jpg").write_bytes(b"image")
            note = p/"note.md"
            note.write_text("![demo](image.jpg)\n*Demo 来源 00:00:01*\n", encoding="utf-8")
            with patch.object(sys, "argv", ["publish", "doc", str(note)]), patch.object(publish.shutil, "which", return_value="lark-cli"), patch.object(publish.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "timeout")) as run:
                for _ in range(2):
                    with self.assertRaises(RuntimeError):
                        publish.main()
                self.assertEqual(run.call_count, 1)

if __name__ == "__main__":
    unittest.main()
